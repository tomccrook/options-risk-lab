import { lazy, Suspense, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
  ReferenceLine,
} from "recharts";
import { submit, jobSchema, replaySchema, type Provenance } from "./api";
import { Action, Evidence, fmt, NumberControl, Status } from "./components";
import type { Controls } from "./Explorer";
import type { AssetModelPoint } from "./modelTypes";
import { request, type Settings } from "./workbench";
function StandardReplay({
  controls,
  settings,
}: {
  controls: Controls;
  settings: Settings;
}) {
  const [policy, setPolicy] = useState("band");
  const [regime, setRegime] = useState("jump-delay");
  const [companion, setCompanion] = useState("nav");
  const [band, setBand] = useState(10);
  const [id, setId] = useState("");
  const [savedId, setSavedId] = useState("");
  const [job, setJob] = useState<ReturnType<typeof jobSchema.parse>>();
  const [error, setError] = useState("");
  const [node, setNode] = useState(0);
  const [evaluation, setEvaluation] = useState<{
    summary: Array<Record<string, string | number>>;
    paired: Array<{
      regime: string;
      spread: number;
      baseline: string;
      rmse_difference: number;
      ci95: number[];
    }>;
    provenance: Provenance;
  }>();
  useEffect(() => {
    if (!id) return;
    const abort = new AbortController();
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const r = await fetch(`/api/jobs/${id}`, { signal: abort.signal });
        if (!r.ok) throw new Error(`Run unavailable (${r.status})`);
        const value = jobSchema.parse(await r.json());
        if (active) {
          setJob(value);
          if (value.status === "running" || value.status === "queued")
            timer = setTimeout(poll, 400);
        }
      } catch (e) {
        if (active && !abort.signal.aborted) setError(String(e));
      }
    }
    void poll();
    return () => {
      active = false;
      abort.abort();
      clearTimeout(timer);
    };
  }, [id]);
  const result =
    job?.status === "complete" ? replaySchema.safeParse(job.result) : undefined;
  const data = result?.success ? result.data : undefined;
  const selected = data?.trace[Math.min(node, data.trace.length - 1)];
  async function run() {
    setError("");
    setJob(undefined);
    setNode(0);
    try {
      const nextId = await submit("/api/jobs/replay", {
        workbench: request(controls, settings),
        replay: {
          policy,
          regime,
          band,
          paths: 128,
          seed: 11,
          steps: 126,
          delay_nodes: regime === "jump-delay" ? 1 : 0,
          share_half_spread: settings.spread,
        },
      });
      setId(nextId);
      setSavedId(nextId);
    } catch (e) {
      setError(String(e));
    }
  }
  async function loadEvaluation() {
    try {
      const r = await fetch("/api/evidence/evaluation");
      if (!r.ok)
        throw new Error(
          "Run uv run orl evaluate --phase locked to generate protected evidence",
        );
      const value = await r.json();
      setEvaluation(value);
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <div className="grid gap-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="space-y-5">
        <h2 className="text-lg font-semibold">A causal hedge policy</h2>
        <label className="block text-sm font-medium">
          Policy
          <select
            aria-label="Replay policy"
            value={policy}
            onChange={(e) => setPolicy(e.target.value)}
            className="mt-2 w-full rounded border border-slate-300 p-2"
          >
            {["none", "daily", "weekly", "monthly", "band"].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="block text-sm font-medium">
          Generator
          <select
            aria-label="Replay generator"
            value={regime}
            onChange={(e) => setRegime(e.target.value)}
            className="mt-2 w-full rounded border border-slate-300 p-2"
          >
            {[
              "matched",
              "physical",
              "misspecified",
              "jump-delay",
              "joint-vol",
            ].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <NumberControl
          label="Delta band"
          value={band}
          min={0}
          max={50}
          unit="shares"
          onChange={setBand}
        />
        <p className="text-xs text-slate-600">
          128 paths, seed 11, 126 nodes across current expiry. Jump: −20% at
          midpoint, one-node execution delay. Misspecified: 30% realised vol
          against 20% IV. Physical drift: 8% annual. Synthetic marks/fills.
        </p>
        <Action
          onClick={run}
          disabled={job?.status === "running" || job?.status === "queued"}
        >
          Run causal replay
        </Action>
        {job?.status === "running" || job?.status === "queued" ? (
          <Action
            onClick={() => {
              void fetch(`/api/jobs/${id}/cancel`, { method: "POST" });
            }}
          >
            Cancel replay
          </Action>
        ) : null}
        <label className="block text-sm font-medium">
          Replay run ID
          <input
            aria-label="Replay run ID"
            value={savedId}
            onChange={(e) => setSavedId(e.target.value)}
            className="mt-2 w-full rounded border border-slate-300 bg-white p-2 font-mono text-xs"
          />
        </label>
        <Action
          disabled={!savedId.trim()}
          onClick={() => {
            setError("");
            setNode(0);
            if (savedId.trim() !== id) setJob(undefined);
            setId(savedId.trim());
          }}
        >
          Load saved replay
        </Action>
        <Action onClick={loadEvaluation}>Load locked evaluation</Action>
        <p className="break-all text-xs text-slate-600">
          {id
            ? `Run ID ${id}`
            : "A run stores the current original book and assumptions."}
        </p>
      </aside>
      <section className="min-w-0">
        <h2 className="text-2xl font-semibold">
          Trace the loss to a cash movement
        </h2>
        <p className="mt-2 mb-6 text-sm text-slate-600">
          Policies receive current observable risk, shares and pending orders.
          Delayed requests fill at later node quotes. Premium remains offset by
          the option liability.
        </p>
        <Status
          pending={job?.status === "running" || job?.status === "queued"}
          error={
            error ||
            job?.error ||
            (!result?.success && result ? "Invalid replay response" : "")
          }
        />
        {data ? (
          <>
            <details className="mb-4 text-sm">
              <summary>
                Original replay configuration · current controls do not change
                this saved run
              </summary>
              <pre
                tabIndex={0}
                role="region"
                aria-label="Original replay manifest"
                className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs"
              >
                {JSON.stringify(job?.manifest, null, 2)}
              </pre>
            </details>
            <p className="mb-4 text-sm">
              Saved run: {data.generator} · first path · {data.quality}.
              Financed error is terminal NAV minus initial allocated capital
              grown at the funding rate.
            </p>
            <label className="mb-3 block text-sm">
              Timeline companion
              <select
                aria-label="Timeline companion"
                value={companion}
                onChange={(e) => setCompanion(e.target.value)}
                className="ml-2 rounded border border-slate-300 p-2"
              >
                <option value="nav">Account NAV USD</option>
                <option value="iv">Assigned IV annual %</option>
              </select>
            </label>
            <div
              className="h-72 rounded-lg border border-slate-200 bg-white p-4"
              role="img"
              aria-label={`First path spot and ${companion} versus elapsed calendar days; node details below`}
            >
              <ResponsiveContainer>
                <LineChart
                  data={data.trace.map((r) => ({
                    ...r,
                    iv_percent: r.iv * 100,
                  }))}
                  margin={{ top: 16, right: 20, left: 15, bottom: 28 }}
                  accessibilityLayer
                >
                  <CartesianGrid stroke="#e2e8f0" vertical={false} />
                  <XAxis
                    dataKey="days"
                    type="number"
                    domain={[0, "dataMax"]}
                    tickCount={6}
                    tickFormatter={(v) => fmt(v, 0)}
                    label={{
                      value: "Elapsed calendar days",
                      position: "bottom",
                      offset: 8,
                    }}
                  />
                  <YAxis
                    yAxisId="spot"
                    width={55}
                    label={{
                      value: "Spot USD",
                      angle: -90,
                      position: "insideLeft",
                    }}
                  />
                  <YAxis
                    yAxisId="nav"
                    orientation="right"
                    width={80}
                    label={{
                      value: companion === "nav" ? "NAV USD" : "IV annual %",
                      angle: 90,
                      position: "insideRight",
                    }}
                  />
                  <Tooltip
                    formatter={(v) => fmt(typeof v === "number" ? v : null, 2)}
                  />
                  <Legend verticalAlign="top" />
                  <ReferenceLine
                    x={selected?.days}
                    stroke="#64748b"
                    yAxisId="spot"
                  />
                  <Line
                    yAxisId="spot"
                    dataKey="spot"
                    name="Spot · solid"
                    stroke="#0f766e"
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="nav"
                    dataKey={companion === "nav" ? "nav" : "iv_percent"}
                    name={companion === "nav" ? "NAV · dashed" : "IV · dashed"}
                    stroke="#334155"
                    strokeDasharray="6 4"
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-5 grid gap-6 sm:grid-cols-[12rem_minmax(0,1fr)]">
              <NumberControl
                label="Replay node"
                value={node}
                min={0}
                max={data.trace.length - 1}
                onChange={setNode}
              />
              <dl className="grid grid-cols-2 gap-3 text-sm tabular-nums">
                {selected
                  ? Object.entries({
                      Day: selected.days,
                      Spot: selected.spot,
                      "Assigned IV annual %": selected.iv * 100,
                      "Requested shares": selected.request,
                      "Filled shares": selected.fill,
                      "Current shares": selected.shares,
                      "Funding USD": selected.funding,
                      "Dividend USD": selected.dividend,
                      "Execution cost USD": selected.cost,
                      "Cash USD": selected.cash,
                      "Option liability USD": selected.option_value,
                      "NAV USD": selected.nav,
                      "Net delta shares": selected.delta_after,
                    }).map(([k, v]) => (
                      <div key={k}>
                        <dt className="text-slate-600">{k}</dt>
                        <dd className="font-medium">{fmt(v, 2)}</dd>
                      </div>
                    ))
                  : null}
              </dl>
            </div>
            <p className="my-3 text-xs text-slate-600">
              Hedge basis: {data.delta_basis}. First-path maximum absolute delta{" "}
              {fmt(data.max_abs_delta[0], 2)} shares; infeasible requests{" "}
              {data.rejected_requests.reduce((a, b) => a + b, 0)} across this
              run.
            </p>
            <details className="my-5">
              <summary>Financed error distribution · independent paths</summary>
              <div
                className="h-56 mt-3"
                role="img"
                aria-label="Histogram of financed terminal errors in USD and independent path counts"
              >
                <ResponsiveContainer>
                  <BarChart
                    data={data.distribution}
                    margin={{ bottom: 24, left: 8, right: 16 }}
                    accessibilityLayer
                  >
                    <CartesianGrid stroke="#e2e8f0" vertical={false} />
                    <XAxis
                      dataKey="error_usd"
                      interval={2}
                      tickFormatter={(v) => fmt(v, 0)}
                      label={{
                        value: "Financed error USD",
                        position: "bottom",
                      }}
                    />
                    <YAxis
                      allowDecimals={false}
                      width={45}
                      label={{
                        value: "Paths",
                        angle: -90,
                        position: "insideLeft",
                      }}
                    />
                    <Tooltip />
                    <Bar
                      dataKey="count"
                      name="Independent paths"
                      fill="#0f766e"
                      isAnimationActive={false}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="text-xs text-slate-600">
                20 equal-width bins. Financed error already includes execution
                costs and funding benchmark.
              </p>
            </details>
            <div
              tabIndex={0}
              role="region"
              aria-label="Exploratory replay metrics"
              className="mt-6 overflow-x-auto"
            >
              <table className="w-full text-sm tabular-nums">
                <caption className="text-left font-medium">
                  128 independent paths · exploratory demo, not locked policy
                  evidence
                </caption>
                <thead>
                  <tr>
                    <th>Mean financed error USD</th>
                    <th>RMSE USD</th>
                    <th>CVaR 95% USD</th>
                    <th>Mean cost USD</th>
                    <th>Mean turnover shares</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    {[
                      "mean",
                      "rmse",
                      "cvar95",
                      "mean_cost",
                      "mean_turnover",
                    ].map((k) => (
                      <td key={k}>{fmt(data.metrics[k], 2)}</td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
            <details className="mt-5">
              <summary>Full cash / fill audit</summary>
              <div
                tabIndex={0}
                role="region"
                aria-label="Full cash and fill audit"
                className="max-h-96 overflow-auto"
              >
                <table className="w-full text-xs tabular-nums">
                  <thead>
                    <tr>
                      {[
                        "Node",
                        "Spot",
                        "Request",
                        "Fill",
                        "Shares",
                        "Cash",
                        "Option value",
                        "NAV",
                        "Cost",
                      ].map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.trace.map((r) => (
                      <tr key={r.node}>
                        {[
                          r.node,
                          r.spot,
                          r.request,
                          r.fill,
                          r.shares,
                          r.cash,
                          r.option_value,
                          r.nav,
                          r.cost,
                        ].map((x, i) => (
                          <td key={i}>{fmt(x, 2)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            <Evidence value={data.provenance} />
          </>
        ) : (
          <p className="rounded-lg border border-slate-200 bg-white p-6">
            Run a replay to inspect the first path's fills, cash and liability.
            Multi-expiry books require a separately validated dynamic roll
            policy.
          </p>
        )}
        {evaluation ? (
          <>
            <h3 className="mt-8 text-xl font-semibold">
              Protected paired evaluation
            </h3>
            <p className="mt-2 text-sm text-slate-600">
              Predeclared seeds 1009, 2027, 3041; 1,024 paths each.
              Independent-path paired bootstrap. Original study assumptions
              retained; current demo controls do not change this evidence.
            </p>
            <div
              tabIndex={0}
              role="region"
              aria-label="Locked evaluation summary"
              className="mt-4 max-h-96 overflow-auto"
            >
              <table className="w-full text-xs tabular-nums">
                <thead>
                  <tr>
                    <th>Regime / spread USD</th>
                    <th>Policy</th>
                    <th>RMSE USD</th>
                    <th>CVaR USD</th>
                    <th>Cost USD</th>
                  </tr>
                </thead>
                <tbody>
                  {evaluation.summary.map((r, i) => (
                    <tr key={i}>
                      <th>
                        {r.regime} / {r.spread}
                      </th>
                      <td>{r.policy}</td>
                      <td>{fmt(Number(r.rmse), 2)}</td>
                      <td>{fmt(Number(r.cvar95), 2)}</td>
                      <td>{fmt(Number(r.mean_cost), 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <details className="mt-3">
              <summary>Band minus fixed policy · paired RMSE intervals</summary>
              <div
                tabIndex={0}
                role="region"
                aria-label="Paired RMSE intervals"
                className="overflow-x-auto"
              >
                <table className="w-full text-xs">
                  <thead>
                    <tr>
                      <th>Regime / spread</th>
                      <th>Baseline</th>
                      <th>Difference USD</th>
                      <th>95% CI USD</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evaluation.paired.map((p, i) => (
                      <tr key={i}>
                        <th>
                          {p.regime} / {p.spread}
                        </th>
                        <td>{p.baseline}</td>
                        <td>{fmt(p.rmse_difference, 2)}</td>
                        <td>{p.ci95.map((x) => fmt(x, 2)).join(" to ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            <Evidence value={evaluation.provenance} />
          </>
        ) : null}
      </section>
    </div>
  );
}

const ModelReplay = lazy(() => import("./ModelReplay"));
export default function Replay({
  controls,
  settings,
  modelMode,
  onModelModeChange,
  modelPoint,
  onUseDefaults,
}: {
  controls: Controls;
  settings: Settings;
  modelMode: boolean;
  onModelModeChange: (value: boolean) => void;
  modelPoint?: AssetModelPoint;
  onUseDefaults: () => void;
}) {
  return (
    <>
      <div
        className="mb-6 flex flex-wrap gap-3"
        role="group"
        aria-label="Replay study selection"
      >
        <Action pressed={!modelMode} onClick={() => onModelModeChange(false)}>
          Standard hedge replay
        </Action>
        <Action pressed={modelMode} onClick={() => onModelModeChange(true)}>
          Model risk replay
        </Action>
      </div>
      <Suspense fallback={<p role="status">Loading model replay…</p>}>
        {modelMode ? (
          <ModelReplay
            controls={controls}
            linkedPoint={modelPoint}
            onUseDefaults={onUseDefaults}
          />
        ) : (
          <StandardReplay controls={controls} settings={settings} />
        )}
      </Suspense>
    </>
  );
}
