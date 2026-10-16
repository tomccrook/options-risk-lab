import { useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { assetReplaySchema, assetStudySchema, useRecordedJob } from "./api";
import { Action, Evidence, fmt, NumberControl, Status } from "./components";
import type { Controls } from "./Explorer";
import type { AssetModelPoint } from "./modelTypes";

export default function ModelReplay({
  controls,
  linkedPoint,
  onUseDefaults,
}: {
  controls: Controls;
  linkedPoint?: AssetModelPoint;
  onUseDefaults: () => void;
}) {
  const [generator, setGenerator] = useState("heston");
  const [hedger, setHedger] = useState("heston-minvariance");
  const [spread, setSpread] = useState(0.01);
  const [delay, setDelay] = useState(1);
  const [node, setNode] = useState(0);
  const [companion, setCompanion] = useState("nav");
  const [study, setStudy] =
    useState<ReturnType<typeof assetStudySchema.parse>>();
  const [studyError, setStudyError] = useState("");
  const [studyBusy, setStudyBusy] = useState(false);
  const replay = useRecordedJob(assetReplaySchema, "orl.asset-replay.v1");
  const data = replay.data;
  const selected = data?.trace[Math.min(node, data.trace.length - 1)];
  async function loadStudy() {
    setStudyBusy(true);
    setStudyError("");
    try {
      const response = await fetch("/api/evidence/model-risk");
      if (!response.ok)
        throw new Error(
          "Protected model study unavailable. Run uv run orl model-evaluate --phase locked.",
        );
      setStudy(assetStudySchema.parse(await response.json()));
    } catch (e) {
      setStudyError(String(e));
    } finally {
      setStudyBusy(false);
    }
  }
  const summary = study?.summary.filter(
    (r) =>
      r.generator === generator && r.spread === spread && r.delay === delay,
  );
  const pairs = study?.paired.filter(
    (r) =>
      r.generator === generator && r.spread === spread && r.delay === delay,
  );
  return (
    <div className="grid gap-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="space-y-5">
        <h2 className="text-lg font-semibold text-balance">
          Separate truth and hedge assumptions
        </h2>
        <label className="block text-sm font-medium">
          Synthetic generator
          <select
            aria-label="Model replay generator"
            value={generator}
            onChange={(e) => setGenerator(e.target.value)}
            className="mt-2 w-full rounded border border-slate-300 p-2"
          >
            <option value="bsm">Risk-neutral GBM</option>
            <option value="merton">Merton random jumps</option>
            <option value="heston">Heston stochastic variance</option>
          </select>
        </label>
        <label className="block text-sm font-medium">
          Audit hedge model
          <select
            aria-label="Audit hedge model"
            value={hedger}
            onChange={(e) => setHedger(e.target.value)}
            className="mt-2 w-full rounded border border-slate-300 p-2"
          >
            {[
              "none",
              "bsm-fixed",
              "bsm-state",
              "merton",
              "heston",
              "heston-minvariance",
              "bsm-weekly",
            ].map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
        </label>
        <label className="block text-sm font-medium">
          Stock half-spread
          <select
            aria-label="Model stock half-spread"
            value={spread}
            onChange={(e) => setSpread(Number(e.target.value))}
            className="mt-2 w-full rounded border border-slate-300 p-2"
          >
            <option value={0}>0 USD/share</option>
            <option value={0.01}>0.01 USD/share</option>
            <option value={0.05}>0.05 USD/share</option>
          </select>
        </label>
        <label className="block text-sm font-medium">
          Execution delay
          <select
            aria-label="Model execution delay"
            value={delay}
            onChange={(e) => setDelay(Number(e.target.value))}
            className="mt-2 w-full rounded border border-slate-300 p-2"
          >
            <option value={0}>0 nodes · idealised</option>
            <option value={1}>1 node · later quote</option>
          </select>
        </label>
        <Action
          disabled={replay.busy}
          onClick={() => {
            setNode(0);
            void replay.run("/api/jobs/model-replay", {
              point: linkedPoint ?? {
                spot: controls.spot,
                strike: controls.strike,
                tau: controls.days / 365,
                rate: controls.rate / 100,
                yield_: controls.yield_ / 100,
                parameters: {
                  diffusion_vol: controls.vol / 100,
                  v0: (controls.vol / 100) ** 2,
                  theta: (controls.vol / 100) ** 2,
                },
              },
              generator,
              selected_hedger: hedger,
              half_spread: spread,
              delay,
              seed: 137,
              paths: 128,
              steps: 126,
              substeps: 4,
            });
          }}
        >
          Run model hedge comparison
        </Action>
        {replay.busy && replay.id ? (
          <Action onClick={() => void replay.cancel()}>
            Cancel model replay
          </Action>
        ) : null}
        <label className="block text-sm">
          Saved model replay ID
          <input
            aria-label="Saved model replay ID"
            value={replay.savedId}
            onChange={(e) => replay.setSavedId(e.target.value)}
            className="mt-2 w-full rounded border border-slate-300 p-2"
          />
        </label>
        <Action
          disabled={replay.busy || !replay.savedId}
          onClick={() => replay.load(replay.savedId)}
        >
          Load saved model replay
        </Action>
        {linkedPoint ? (
          <div className="space-y-2 rounded border border-teal-200 bg-teal-50 p-3 text-xs">
            <p data-testid="linked-model-config">
              Linked pricing assumptions: S {linkedPoint.spot}, K{" "}
              {linkedPoint.strike}, {Math.round(linkedPoint.tau * 365)} days,
              lambda {linkedPoint.parameters.intensity}, xi{" "}
              {linkedPoint.parameters.vol_of_vol}, rho{" "}
              {linkedPoint.parameters.rho}. These shape parameters and contract
              are used for new replay runs; initial premiums matched.
            </p>
            <Action onClick={onUseDefaults}>
              Use current explorer defaults
            </Action>
          </div>
        ) : null}
        <p className="text-xs text-slate-600 text-pretty">
          Dedicated control: short one call + one put ×100, initial stock zero,
          allocated capital 10,000 USD. Global book and smile controls do not
          apply. Shared spot/strike/maturity/rates/base IV apply to new runs.
          Jump/Heston shape parameters use linked pricing assumptions when
          present, otherwise defaults; original fitted parameters are saved.
        </p>
        <p className="text-xs text-slate-600 text-pretty">
          All models receive the same present spot and variance signal. Initial
          premiums match at one contract. BSM-state scales IV by the observed
          variance ratio. Heston-minvariance adds the instantaneous correlation
          term to partial delta. Stock-only hedging leaves jump and independent
          variance risk.
        </p>
      </aside>
      <section className="min-w-0 space-y-5">
        <h2 className="text-2xl font-semibold text-balance">
          Does a different model improve the paid hedge?
        </h2>
        <p className="text-sm text-slate-600 text-pretty">
          Same paths, premium, option marks, information, integer shares and
          capital constraints. Every trade, financing flow, option settlement
          and stock liquidation uses the shared self-financing ledger.
        </p>
        <p className="text-xs text-slate-600">
          126 equal decision nodes over the contract horizon; hedges trade every
          node, bsm-weekly every five nodes. These identifiers do not mean
          literal calendar-day/week schedules.
        </p>
        <Status pending={replay.busy} error={replay.error} />
        {data ? (
          <>
            <div
              className="rounded-lg border border-teal-200 bg-teal-50 p-4 text-sm"
              data-testid="model-replay-saved"
            >
              Saved model replay: {data.config.generator} ·{" "}
              {data.selected_hedger} · seed {data.config.seed} ·{" "}
              {data.config.paths} paths · {data.config.steps} nodes ·
              half-spread {fmt(data.config.half_spread, 2)} · delay{" "}
              {data.config.delay}. Original assumptions; current controls do not
              modify this run.
            </div>
            <p className="text-sm">
              Entry option premium received {fmt(data.entry_premium_usd, 2)} USD
              offsets an equal liability. Allocated NAV {fmt(data.allocated, 2)}{" "}
              USD before 10 USD option-entry costs. Funding benchmark{" "}
              {fmt(data.funding_benchmark, 2)} USD. Current variance is an
              idealised observable; no future states passed to a policy.
            </p>
            <div
              tabIndex={0}
              role="region"
              aria-label="Exploratory model hedge metrics"
              className="overflow-x-auto"
            >
              <table className="w-full text-xs tabular-nums">
                <caption className="text-left font-medium">
                  {data.config.paths}-path exploratory comparison · financed
                  replication errors, USD
                </caption>
                <thead>
                  <tr>
                    <th>Hedger</th>
                    <th>Mean</th>
                    <th>RMSE</th>
                    <th>95% ES loss</th>
                    <th>Mean paid cost</th>
                    <th>Mean share turnover</th>
                    <th>Rejected requests</th>
                  </tr>
                </thead>
                <tbody>
                  {data.summary.map((r) => (
                    <tr key={r.hedger}>
                      <th>{r.hedger}</th>
                      <td>{fmt(r.mean, 2)}</td>
                      <td>{fmt(r.rmse, 2)}</td>
                      <td>{fmt(r.cvar95, 2)}</td>
                      <td>{fmt(r.mean_cost, 2)}</td>
                      <td>{fmt(r.mean_turnover, 1)}</td>
                      <td>{r.rejected_requests}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div
              className="h-72 rounded-lg border border-slate-200 p-3"
              role="img"
              aria-label="First seeded model replay path, spot and account NAV; cash audit below"
            >
              <ResponsiveContainer>
                <LineChart
                  data={data.trace}
                  margin={{ top: 15, right: 12, left: 6, bottom: 22 }}
                  accessibilityLayer
                >
                  <CartesianGrid stroke="#e2e8f0" />
                  <XAxis
                    type="number"
                    dataKey="days"
                    tickCount={6}
                    tickFormatter={(x) => fmt(x, 0)}
                    label={{
                      value: "Elapsed calendar days",
                      position: "insideBottom",
                      offset: -10,
                    }}
                  />
                  <YAxis
                    yAxisId="spot"
                    domain={([low, high]) => [low - 5, high + 5]}
                    width={65}
                    tickFormatter={(x) => fmt(x, 0)}
                    label={{
                      value: "Spot USD",
                      angle: -90,
                      position: "insideLeft",
                    }}
                  />
                  <YAxis
                    yAxisId="nav"
                    domain={
                      companion === "nav"
                        ? ([low, high]) => [low - 50, high + 50]
                        : ["dataMin", "dataMax"]
                    }
                    orientation="right"
                    width={80}
                    tickFormatter={(x) => fmt(x, companion === "nav" ? 0 : 3)}
                    label={{
                      value: companion === "nav" ? "NAV USD" : "Variance /year",
                      angle: 90,
                      position: "insideRight",
                    }}
                  />
                  <Tooltip />
                  <Legend verticalAlign="top" />
                  <Line
                    yAxisId="spot"
                    dataKey="spot"
                    stroke="#334155"
                    name="Spot"
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="nav"
                    dataKey={companion}
                    stroke="#0f766e"
                    name={
                      companion === "nav"
                        ? "NAV after paid fills"
                        : "Observed variance"
                    }
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <label className="block text-sm">
              Model timeline companion{" "}
              <select
                aria-label="Model timeline companion"
                value={companion}
                onChange={(e) => setCompanion(e.target.value)}
                className="ml-3 rounded border border-slate-300 p-2"
              >
                <option value="nav">Account NAV USD</option>
                <option value="variance">Observed variance /year</option>
              </select>
            </label>
            <NumberControl
              label="Model replay node"
              value={node}
              min={0}
              max={data.trace.length - 1}
              onChange={setNode}
            />
            {selected ? (
              <dl className="grid grid-cols-2 gap-4 rounded-lg bg-slate-50 p-4 text-sm tabular-nums sm:grid-cols-4">
                {[
                  ["Spot USD", selected.spot],
                  ["Observed variance", selected.variance],
                  ["Requested shares", selected.request],
                  ["Filled shares", selected.fill],
                  ["Stock inventory", selected.shares],
                  ["Cash USD", selected.cash],
                  ["Option liability USD", selected.option_value],
                  ["NAV USD", selected.nav],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <dt className="text-slate-600">{label}</dt>
                    <dd className="mt-1 font-medium">
                      {fmt(
                        value as number,
                        String(label).includes("variance") ? 6 : 2,
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : null}
            <details>
              <summary>Full model replay cash audit</summary>
              <div
                tabIndex={0}
                role="region"
                aria-label="Model cash audit"
                className="mt-3 max-h-80 overflow-auto"
              >
                <table className="w-full text-xs tabular-nums">
                  <thead>
                    <tr>
                      {[
                        "Node",
                        "Spot",
                        "Variance",
                        "Request",
                        "Fill",
                        "Shares",
                        "Funding",
                        "Dividend",
                        "Cost",
                        "Cash",
                        "Option value",
                        "NAV",
                      ].map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.trace.map((r) => (
                      <tr key={r.node}>
                        <th>{r.node}</th>
                        {[
                          r.spot,
                          r.variance,
                          r.request,
                          r.fill,
                          r.shares,
                          r.funding,
                          r.dividend,
                          r.cost,
                          r.cash,
                          r.option_value,
                          r.nav,
                        ].map((v, i) => (
                          <td key={i}>{fmt(v, i === 1 ? 6 : 2)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            <details>
              <summary>
                Exploratory paired uncertainty and saved assumptions
              </summary>
              <div
                tabIndex={0}
                role="region"
                aria-label="Exploratory paired model uncertainty"
                className="my-3 overflow-x-auto"
              >
                <table className="w-full text-xs tabular-nums">
                  <thead>
                    <tr>
                      <th>Hedge minus BSM-state</th>
                      <th>RMSE difference USD</th>
                      <th>95% paired path CI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.paired.map((r) => (
                      <tr key={r.hedger}>
                        <th>{r.hedger}</th>
                        <td>{fmt(r.rmse_difference, 2)}</td>
                        <td>[{r.ci95.map((x) => fmt(x, 2)).join(", ")}]</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <pre
                tabIndex={0}
                aria-label="Original model replay assumptions"
                className="max-h-64 overflow-auto text-xs"
              >
                {JSON.stringify(
                  {
                    manifest: replay.manifest,
                    fitted_parameters: data.parameters,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
            <p className="text-xs text-slate-600">
              {data.warning} {data.numerical_quality.adaptive_refinements}{" "}
              adaptive numerical refinements; unresolved integrations reject the
              job.
            </p>
            <Evidence value={data.provenance} />
          </>
        ) : (
          <p className="rounded-lg border border-slate-200 p-5 text-sm text-slate-600">
            Run the seven hedge baselines on a common synthetic path set, or
            load a saved run ID.
          </p>
        )}
        <div className="border-t border-slate-200 pt-6">
          <h3 className="text-xl font-semibold text-balance">
            Protected model-risk evaluation
          </h3>
          <p className="mt-2 text-sm text-slate-600">
            Generator, spread and delay controls select the evidence cell below.
            This study uses its own frozen ATM one-year contract and parameters,
            independent of current explorer controls. Compare every BSM
            baseline, not a selected weak opponent.
          </p>
          <div className="my-4">
            <Action disabled={studyBusy} onClick={() => void loadStudy()}>
              Load protected model evaluation
            </Action>
            <a
              href="/api/reports/models"
              className="ml-4 text-sm text-teal-800 underline"
            >
              Model-risk report
            </a>
          </div>
          <Status pending={studyBusy} error={studyError} />
          {study ? (
            <>
              <p className="text-sm" data-testid="protected-model-evidence">
                {study.episodes.rows.toLocaleString()} episode rows · run{" "}
                {study.run_id} · 3,072 paths / cell · 154 tail observations.
                Intervals condition on the synthetic generator; nodes are not
                independent samples.
              </p>
              <div
                tabIndex={0}
                role="region"
                aria-label="Protected asset model hedge metrics"
                className="mt-4 overflow-x-auto"
              >
                <table className="w-full text-xs tabular-nums">
                  <caption className="text-left font-medium">
                    {generator} / {spread} USD half-spread / delay {delay} · all
                    signed errors and paid costs USD
                  </caption>
                  <thead>
                    <tr>
                      <th>Hedger</th>
                      <th>Mean</th>
                      <th>RMSE</th>
                      <th>ES95 loss</th>
                      <th>ES95 CI</th>
                      <th>Paid cost</th>
                      <th>Rejected requests</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary?.map((r) => (
                      <tr key={r.hedger}>
                        <th>{r.hedger}</th>
                        <td>{fmt(r.mean, 2)}</td>
                        <td>{fmt(r.rmse, 2)}</td>
                        <td>{fmt(r.cvar95, 2)}</td>
                        <td>
                          [{r.cvar95_ci95.map((x) => fmt(x, 2)).join(", ")}]
                        </td>
                        <td>{fmt(r.mean_cost, 2)}</td>
                        <td>{r.rejected_requests}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div
                tabIndex={0}
                role="region"
                aria-label="Protected paired asset model comparisons"
                className="mt-4 overflow-x-auto"
              >
                <table className="w-full text-xs tabular-nums">
                  <caption className="text-left font-medium">
                    Candidate minus baseline · negative RMSE difference favours
                    candidate; ≥5% and CI below zero required per baseline
                  </caption>
                  <thead>
                    <tr>
                      <th>Candidate</th>
                      <th>BSM baseline</th>
                      <th>RMSE difference USD</th>
                      <th>95% paired CI</th>
                      <th>Threshold supported</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pairs?.map((r, i) => (
                      <tr key={i}>
                        <th>{r.hedger}</th>
                        <td>{r.baseline}</td>
                        <td>{fmt(r.rmse_difference, 2)}</td>
                        <td>[{r.ci95.map((x) => fmt(x, 2)).join(", ")}]</td>
                        <td>
                          {r.supports_threshold ? "yes, this comparison" : "no"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 break-all text-xs text-slate-600">
                Protected protocol SHA256 {study.protocol_sha256} · episode
                payload SHA256 {study.episodes.sha256}
              </p>
              <Evidence value={study.provenance} />
            </>
          ) : null}
        </div>
      </section>
    </div>
  );
}
