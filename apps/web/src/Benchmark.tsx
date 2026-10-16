import { lazy, Suspense, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { studySchema, probeSchema, useService } from "./api";
import { Action, Evidence, fmt, NumberControl, Status } from "./components";
import type { Controls } from "./Explorer";
import type { AssetModelPoint } from "./modelTypes";
function SurrogateBenchmark({ controls }: { controls: Controls }) {
  const [study, setStudy] = useState<ReturnType<typeof studySchema.parse>>();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(true);
  const [target, setTarget] = useState("american");
  const [method, setMethod] = useState("derivative-aware");
  const [split, setSplit] = useState("boundary");
  const [m, setM] = useState(controls.spot / controls.strike);
  const [days, setDays] = useState(controls.days);
  const [vol, setVol] = useState(controls.vol);
  useEffect(() => {
    const abort = new AbortController();
    let active = true;
    async function load() {
      try {
        const r = await fetch("/api/evidence/ml", { signal: abort.signal });
        if (!r.ok)
          throw new Error(
            "No completed ML evidence. Generate it with uv run orl train; failures remain in the job registry.",
          );
        const value = studySchema.parse(await r.json());
        if (active) {
          setStudy(value);
          setPending(false);
        }
      } catch (e) {
        if (active && !abort.signal.aborted) {
          setError(String(e));
          setPending(false);
        }
      }
    }
    void load();
    return () => {
      active = false;
      abort.abort();
    };
  }, []);
  const probe = useService(
    "/api/model-probe",
    {
      target,
      method,
      m,
      tau: days / 365,
      vol: vol / 100,
      rate: controls.rate / 100,
      yield_: controls.yield_ / 100,
    },
    probeSchema,
  );
  const rows = study?.metrics.filter(
    (r) => r.target === target && r.split === split,
  );
  const grouped = ["grid", "price-only", "derivative-aware"].map((method) => {
    const data = rows?.filter((r) => r.method === method) ?? [];
    return {
      method,
      delta: data.reduce((a, r) => a + r.rmse.delta, 0) / (data.length || 1),
    };
  });
  return (
    <div className="grid gap-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="space-y-5">
        <h2 className="text-lg font-semibold">Probe model trust</h2>
        <label className="block text-sm font-medium">
          Numerical target
          <select
            aria-label="Numerical target"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className="mt-2 w-full rounded border border-slate-300 p-2"
          >
            <option value="american">Synthetic American put</option>
            <option value="european">European analytical control</option>
          </select>
        </label>
        <label className="block text-sm font-medium">
          Surrogate arm
          <select
            aria-label="Surrogate arm"
            value={method}
            onChange={(e) => setMethod(e.target.value)}
            className="mt-2 w-full rounded border border-slate-300 p-2"
          >
            <option>derivative-aware</option>
            <option>price-only</option>
          </select>
        </label>
        <NumberControl
          label="Moneyness S/K"
          value={m}
          min={0.5}
          max={1.6}
          step={0.01}
          onChange={setM}
        />
        <NumberControl
          label="Probe maturity"
          value={days}
          min={1}
          max={730}
          onChange={setDays}
          unit="calendar days"
        />
        <NumberControl
          label="Probe volatility"
          value={vol}
          min={5}
          max={80}
          step={0.5}
          onChange={setVol}
          unit="% annual"
        />
        <Action
          onClick={() => {
            setM(0.85);
            setDays(7);
            setVol(20);
          }}
        >
          Inspect exercise boundary
        </Action>
        <p className="text-xs text-slate-600">
          Reference strike 100 USD; American target is a constant-carry
          numerical pricing/risk study, with no traded assignment lifecycle.
        </p>
      </aside>
      <section className="min-w-0">
        <h2 className="text-2xl font-semibold">
          Price accuracy does not certify a hedge
        </h2>
        <p className="my-3 text-sm text-slate-600">
          Price-only versus price-and-delta tanh MLPs. Same 2,048 examples, 300
          full-batch updates, architecture, derivative graph and seeds 17/31/47.
          All models CPU float64.
        </p>
        <Status pending={probe.pending} error={probe.error} />
        {probe.data ? (
          <>
            <div className="my-5 rounded-lg border border-teal-200 bg-teal-50 p-5">
              <h3 className="font-semibold" data-testid="active-engine">
                Active engine: {probe.data.engine}
              </h3>
              <p className="mt-2 text-sm">
                {probe.data.reason} · No post-hoc clipping. Raw derivatives
                remain visible for diagnosis.
              </p>
            </div>
            <div
              tabIndex={0}
              role="region"
              aria-label="Live model probe"
              className="overflow-x-auto"
            >
              <table className="w-full text-sm tabular-nums">
                <caption className="text-left font-medium">
                  Live probe · raw surrogate seed 17 · K=100 · decimal IV
                  derivatives
                </caption>
                <thead>
                  <tr>
                    <th>Engine</th>
                    <th>Price USD/share</th>
                    <th>Delta</th>
                    <th>Gamma /USD</th>
                    <th>Vega /decimal IV</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ["Reference", probe.data.reference],
                    ["Raw surrogate", probe.data.raw_surrogate],
                    ["Active result", probe.data.active],
                  ].map(([label, values]) => (
                    <tr key={String(label)}>
                      <th scope="row">{String(label)}</th>
                      {(Array.isArray(values)
                        ? values
                        : [null, null, null, null]
                      ).map((v, i) => (
                        <td key={i}>{fmt(v, i === 2 ? 6 : 4)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-slate-600">
              Live single-query reference {fmt(probe.data.reference_ms, 2)} ms /
              raw inference {fmt(probe.data.raw_inference_ms, 2)} ms; diagnostic
              timings only, cold import/model-loading excluded. Total handler
              including loading: {fmt(probe.data.total_ms, 2)} ms.{" "}
              {probe.data.quality}. Fair full batch benchmarks below.
            </p>
          </>
        ) : null}
        <h3 className="mt-8 text-xl font-semibold">Protected model study</h3>
        <Status pending={pending} error={error} />
        {study ? (
          <>
            <label className="my-4 block text-sm">
              Evaluation region
              <select
                aria-label="Evaluation region"
                value={split}
                onChange={(e) => setSplit(e.target.value)}
                className="ml-3 rounded border border-slate-300 p-2"
              >
                {["iid", "held-region", "boundary", "ood"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            <div
              className="h-56 rounded-lg border border-slate-200 bg-white p-4"
              role="img"
              aria-label="Mean delta RMSE by method for selected target and region; seed-level table follows"
            >
              <ResponsiveContainer>
                <BarChart
                  data={grouped}
                  margin={{ top: 12, right: 20, left: 12, bottom: 10 }}
                  accessibilityLayer
                >
                  <CartesianGrid stroke="#e2e8f0" vertical={false} />
                  <XAxis dataKey="method" />
                  <YAxis
                    width={70}
                    label={{
                      value: "Delta RMSE",
                      angle: -90,
                      position: "insideLeft",
                    }}
                  />
                  <Tooltip />
                  <Bar
                    dataKey="delta"
                    name="Mean delta RMSE"
                    fill="#0f766e"
                    isAnimationActive={false}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div
              tabIndex={0}
              role="region"
              aria-label="Protected model errors"
              className="mt-5 overflow-x-auto"
            >
              <table className="w-full text-xs tabular-nums">
                <caption className="text-left font-medium">
                  256 points / region, same points across seeds and arms · lower
                  error is better
                </caption>
                <thead>
                  <tr>
                    <th>Method / seed</th>
                    <th>Price RMSE</th>
                    <th>Delta RMSE</th>
                    <th>Gamma RMSE</th>
                    <th>Vega RMSE</th>
                    <th>Bound / shape failures</th>
                    <th>Reference fallback points</th>
                    <th>Scenario error USD / contract</th>
                  </tr>
                </thead>
                <tbody>
                  {rows?.map((r, i) => (
                    <tr key={i}>
                      <th>
                        {r.method} / {r.seed ?? "grid"}
                      </th>
                      {["price", "delta", "gamma", "vega"].map((k) => (
                        <td key={k}>{fmt(r.rmse[k], k === "gamma" ? 6 : 4)}</td>
                      ))}
                      <td>
                        {r.bounds_failures} / {r.shape_failures}
                      </td>
                      <td>
                        {r.fallback_points ?? 0} / {r.samples}
                      </td>
                      <td>{fmt(r.scenario_change_rmse_1_contract_usd, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-4 text-sm">
              Global risk acceptance:{" "}
              {["price-only", "derivative-aware"]
                .map(
                  (method) =>
                    `${method}: ${study.accepted[`${target}/${method}`] ? "accepted" : "rejected"}`,
                )
                .join(" · ")}
              . {study.fallback}.
            </p>
            <details className="mt-5">
              <summary>Budget, convergence and fair timings</summary>
              <p className="my-3 text-sm">
                {study.budget}. Reference mesh 512 versus 1024 and CRR 4096
                selected-probe gate:{" "}
                {study.reference_gate.passed ? "passed" : "failed"}. Grid
                excludes held-region labels and falls back for missing
                cells/OOD. Piecewise-linear interpolation has unreliable gamma
                at knots.
              </p>
              <div
                tabIndex={0}
                role="region"
                aria-label="Full benchmark timings"
                className="max-h-80 overflow-auto"
              >
                <table className="w-full text-xs tabular-nums">
                  <thead>
                    <tr>
                      <th>Method / seed</th>
                      <th>Region</th>
                      <th>Batch</th>
                      <th>p50 ms</th>
                      <th>p95 ms</th>
                    </tr>
                  </thead>
                  <tbody>
                    {study.timings
                      .filter((r) => r.target === target)
                      .map((r, i) => (
                        <tr key={i}>
                          <th>
                            {r.method} / {r.seed ?? "reference"}
                          </th>
                          <td>{r.split ?? "iid"}</td>
                          <td>{r.batch}</td>
                          <td>{fmt(r.p50_ms, 3)}</td>
                          <td>{fmt(r.p95_ms, 3)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </details>
            <Evidence value={study.provenance} />
          </>
        ) : null}
      </section>
    </div>
  );
}

const ModelComparison = lazy(() => import("./ModelComparison"));
export default function Benchmark({
  controls,
  onModelReplay,
}: {
  controls: Controls;
  onModelReplay: (point: AssetModelPoint) => void;
}) {
  const [mode, setMode] = useState("surrogates");
  return (
    <>
      <div
        className="mb-6 flex flex-wrap gap-3"
        role="group"
        aria-label="Benchmark study selection"
      >
        <Action
          pressed={mode === "surrogates"}
          onClick={() => setMode("surrogates")}
        >
          Surrogate accuracy study
        </Action>
        <Action pressed={mode === "models"} onClick={() => setMode("models")}>
          Pricing models & Monte Carlo
        </Action>
      </div>
      <Suspense fallback={<p role="status">Loading model comparison…</p>}>
        {mode === "models" ? (
          <ModelComparison controls={controls} onReplay={onModelReplay} />
        ) : (
          <SurrogateBenchmark controls={controls} />
        )}
      </Suspense>
    </>
  );
}
