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
import {
  assetComparisonSchema,
  mcComparisonSchema,
  useRecordedJob,
  useService,
} from "./api";
import { Action, Evidence, fmt, NumberControl, Status } from "./components";
import type { Controls } from "./Explorer";
import type { AssetModelPoint } from "./modelTypes";

export default function ModelComparison({
  controls,
  onReplay,
}: {
  controls: Controls;
  onReplay: (point: AssetModelPoint) => void;
}) {
  const [match, setMatch] = useState(true);
  const [intensity, setIntensity] = useState(0.4);
  const [jumpMean, setJumpMean] = useState(-0.08);
  const [jumpStd, setJumpStd] = useState(0.12);
  const [xi, setXi] = useState(0.4);
  const [rho, setRho] = useState(-0.7);
  const [kappa, setKappa] = useState(2);
  const [measure, setMeasure] = useState("delta");
  const [paths, setPaths] = useState(16384);
  const [steps, setSteps] = useState(128);
  const config = {
    point: {
      spot: controls.spot,
      strike: controls.strike,
      tau: controls.days / 365,
      rate: controls.rate / 100,
      yield_: controls.yield_ / 100,
      parameters: {
        diffusion_vol: controls.vol / 100,
        v0: (controls.vol / 100) ** 2,
        theta: (controls.vol / 100) ** 2,
        intensity,
        jump_mean: jumpMean,
        jump_std: jumpStd,
        vol_of_vol: xi,
        rho,
        kappa,
      },
    },
    match_premium: match,
  };
  const comparison = useService(
    "/api/models/compare",
    config,
    assetComparisonSchema,
  );
  const mc = useRecordedJob(mcComparisonSchema, "orl.model-mc.v1");
  const data = comparison.data;
  return (
    <div className="grid gap-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="space-y-4">
        <h2 className="text-lg font-semibold text-balance">
          Declare the dynamics
        </h2>
        <p className="text-sm text-slate-600 text-pretty">
          Shared spot, strike, maturity, rates and base volatility come from
          Greek explorer. European cash-settled synthetic controls; these model
          parameters are risk-neutral assumptions.
        </p>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={match}
            onChange={(e) => setMatch(e.target.checked)}
            className="mt-1"
          />
          Match initial premium at selected contract
        </label>
        <NumberControl
          label="Jump intensity"
          value={intensity}
          min={0}
          max={3}
          step={0.1}
          onChange={setIntensity}
          unit="events/year"
        />
        <NumberControl
          label="Mean log jump"
          value={jumpMean}
          min={-0.4}
          max={0.4}
          step={0.01}
          onChange={setJumpMean}
        />
        <NumberControl
          label="Log jump standard deviation"
          value={jumpStd}
          min={0}
          max={0.5}
          step={0.01}
          onChange={setJumpStd}
        />
        <NumberControl
          label="Variance mean reversion"
          value={kappa}
          min={0.25}
          max={8}
          step={0.25}
          onChange={setKappa}
          unit="1/year"
        />
        <NumberControl
          label="Volatility of variance"
          value={xi}
          min={0}
          max={1}
          step={0.05}
          onChange={setXi}
        />
        <NumberControl
          label="Spot/variance correlation"
          value={rho}
          min={-0.95}
          max={0.95}
          step={0.05}
          onChange={setRho}
        />
        <p className="text-xs text-slate-600 text-pretty">
          Matching fits Merton diffusion sigma and Heston v0=theta. Jump shape,
          kappa, xi and rho remain fixed. An infeasible match reports an error.
          This fits one price, not a market surface.
        </p>
        <Action onClick={() => onReplay(config.point)}>
          Compare paid model hedges
        </Action>
        <p className="text-xs text-slate-600">
          This carries the current dynamics and contract into replay. Replay
          always matches initial premiums to isolate hedge-model effects.
        </p>
      </aside>
      <section className="min-w-0 space-y-5">
        <div>
          <h2 className="text-2xl font-semibold text-balance">
            Same premium, different risk
          </h2>
          <p className="mt-2 text-sm text-slate-600 text-pretty">
            Black–Scholes–Merton uses constant volatility. Merton adds random
            jumps. Heston lets variance evolve. Monte Carlo estimates prices
            within a chosen model; it is a numerical engine.
          </p>
        </div>
        <Status pending={comparison.pending} error={comparison.error} />
        {data ? (
          <>
            <p
              className="rounded-lg border border-teal-200 bg-teal-50 p-4 text-sm"
              data-testid="model-match-basis"
            >
              {data.basis} · {controls.spot} / {controls.strike} USD ·{" "}
              {controls.days} days. Vega sensitivities use different parameter
              definitions.
            </p>
            <div
              tabIndex={0}
              role="region"
              aria-label="Asset model prices and Greeks"
              className="overflow-x-auto"
            >
              <table className="w-full text-sm tabular-nums">
                <caption className="text-left font-medium">
                  Selected European call · per option share
                </caption>
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Price USD</th>
                    <th>Delta</th>
                    <th>Gamma /USD</th>
                    <th>Parameter vega</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.model}>
                      <th scope="row">{row.label}</th>
                      <td data-testid={`${row.model}-model-price`}>
                        {fmt(row.price, 6)}
                      </td>
                      <td>{fmt(row.delta, 5)}</td>
                      <td>{fmt(row.gamma, 6)}</td>
                      <td>
                        {fmt(row.vega, 4)}
                        <span className="block text-xs font-normal text-slate-600">
                          {row.vega_basis}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <label className="block text-sm font-medium">
              Model curve measure{" "}
              <select
                aria-label="Model curve measure"
                value={measure}
                onChange={(e) => setMeasure(e.target.value)}
                className="ml-3 rounded border border-slate-300 p-2"
              >
                <option value="price">Call price USD/share</option>
                <option value="delta">Call delta</option>
                <option value="gamma">Call gamma /USD</option>
              </select>
            </label>
            <div
              role="img"
              aria-label={`European call ${measure} by spot across models; selected values and curve table available`}
              className="h-72 rounded-lg border border-slate-200 p-3"
            >
              <ResponsiveContainer>
                <LineChart
                  data={data.curves}
                  margin={{ top: 15, right: 12, left: 14, bottom: 20 }}
                  accessibilityLayer
                >
                  <CartesianGrid stroke="#e2e8f0" />
                  <XAxis
                    dataKey="spot"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    label={{
                      value: "Spot USD · strike fixed",
                      position: "insideBottom",
                      offset: -12,
                    }}
                  />
                  <YAxis
                    width={72}
                    tickFormatter={(v) => fmt(v, measure === "gamma" ? 3 : 2)}
                    label={{
                      value:
                        measure === "price"
                          ? "USD/share"
                          : measure === "gamma"
                            ? "Gamma /USD"
                            : "Delta",
                      angle: -90,
                      position: "insideLeft",
                    }}
                  />
                  <Tooltip />
                  <Legend verticalAlign="top" />
                  {["bsm", "merton", "heston"].map((model, index) => (
                    <Line
                      key={model}
                      dataKey={`${model}_${measure}`}
                      name={["BSM", "Merton jump", "Heston"][index]}
                      stroke={["#334155", "#64748b", "#0f766e"][index]}
                      strokeDasharray={index === 1 ? "6 4" : undefined}
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <details>
              <summary className="cursor-pointer font-medium">
                Curve data and model parameters
              </summary>
              <div
                tabIndex={0}
                role="region"
                aria-label="Asset model curve data"
                className="mt-3 max-h-64 overflow-auto"
              >
                <table className="w-full text-xs tabular-nums">
                  <thead>
                    <tr>
                      <th>Spot USD</th>
                      <th>BSM {measure}</th>
                      <th>Merton {measure}</th>
                      <th>Heston {measure}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.curves.map((row) => (
                      <tr key={row.spot}>
                        <th>{fmt(row.spot, 2)}</th>
                        {["bsm", "merton", "heston"].map((m) => (
                          <td key={m}>{fmt(row[`${m}_${measure}`], 6)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <pre
                className="mt-3 max-h-64 overflow-auto rounded bg-slate-50 p-3 text-xs"
                tabIndex={0}
                aria-label="Fitted synthetic parameters"
              >
                {JSON.stringify(
                  data.rows.map((r) => ({
                    model: r.model,
                    parameters: r.parameters,
                  })),
                  null,
                  2,
                )}
              </pre>
            </details>
            <details>
              <summary className="cursor-pointer font-medium">
                Full repricing versus local spot Greeks
              </summary>
              <p className="my-3 text-sm">
                Unhedged short call + put ×100. Time advances by{" "}
                {fmt(data.scenarios[0]?.days, 1)} days. Diffusion/current
                variance frozen; spot Taylor omits time and cross terms. These
                are mark changes, not executed financed P&amp;L.
              </p>
              <div
                tabIndex={0}
                role="region"
                aria-label="Asset model scenario repricing"
                className="overflow-x-auto"
              >
                <table className="w-full text-xs tabular-nums">
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Spot shock</th>
                      <th>Full change USD</th>
                      <th>Spot Taylor USD</th>
                      <th>Residual USD</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.scenarios.map((row, i) => (
                      <tr key={i}>
                        <th>{row.model}</th>
                        <td>{fmt(row.spot_return * 100, 0)}%</td>
                        <td>{fmt(row.full_change, 2)}</td>
                        <td>{fmt(row.spot_taylor, 2)}</td>
                        <td>{fmt(row.residual, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            <p className="text-xs text-slate-600">
              Independent checks:{" "}
              {data.numerical_checks
                .map(
                  (r) =>
                    `${r.model}: ${r.reference}, price difference ${r.price_error.toExponential(2)} USD, ${r.adaptive_refinements} adaptive refinements`,
                )
                .join(" · ")}
              . Handler {fmt(data.total_ms, 1)} ms; not a runtime contest
              between models.
            </p>
            <Evidence value={data.provenance} />
          </>
        ) : null}
        <div className="border-t border-slate-200 pt-6">
          <h3 className="text-xl font-semibold text-balance">
            Does Monte Carlo recover the reference?
          </h3>
          <p className="mt-2 text-sm text-slate-600 text-pretty">
            Exact terminal GBM/Merton sampling; Heston QE with martingale
            correction. Same requested path budget. Price/pathwise delta,
            common-random-number gamma and volatility bumps. Confidence
            intervals exclude bump and time-step bias.
          </p>
          <div className="my-4 flex flex-wrap items-end gap-4">
            <label className="text-sm">
              MC paths{" "}
              <select
                aria-label="MC paths"
                value={paths}
                onChange={(e) => setPaths(Number(e.target.value))}
                className="ml-2 rounded border border-slate-300 p-2"
              >
                {[4096, 16384, 65536].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              Heston MC steps{" "}
              <select
                aria-label="Heston MC steps"
                value={steps}
                onChange={(e) => setSteps(Number(e.target.value))}
                className="ml-2 rounded border border-slate-300 p-2"
              >
                {[64, 128, 256].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
            <Action
              disabled={mc.busy}
              onClick={() =>
                void mc.run("/api/jobs/model-mc", {
                  ...config,
                  paths,
                  steps,
                  seed: 811,
                })
              }
            >
              Run Monte Carlo comparison
            </Action>
            {mc.busy && mc.id ? (
              <Action onClick={() => void mc.cancel()}>Cancel MC run</Action>
            ) : null}
          </div>
          <Status pending={mc.busy} error={mc.error} />
          {mc.data ? (
            <>
              <p className="my-3 text-sm" data-testid="mc-saved">
                Saved Monte Carlo run {mc.id} · original assumptions below;
                current controls do not alter this result.
              </p>
              <div
                tabIndex={0}
                role="region"
                aria-label="Monte Carlo numerical error"
                className="overflow-x-auto"
              >
                <table className="w-full text-xs tabular-nums">
                  <caption className="text-left font-medium">
                    Estimates ± sampling uncertainty · separate price and Greek
                    errors
                  </caption>
                  <thead>
                    <tr>
                      <th>Model / paths / steps</th>
                      <th>Quantity</th>
                      <th>MC estimate</th>
                      <th>Reference</th>
                      <th>Error</th>
                      <th>95% sampling CI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mc.data.rows.flatMap((row) =>
                      ["price", "delta", "gamma", "vega"].map((key) => {
                        const g = row.greeks[key as keyof typeof row.greeks];
                        return (
                          <tr key={`${row.model}-${key}`}>
                            <th>
                              {row.model} / {row.paths} / {row.steps}
                            </th>
                            <td>{key}</td>
                            <td>{fmt(g.value, key === "gamma" ? 6 : 4)}</td>
                            <td>{fmt(g.reference, key === "gamma" ? 6 : 4)}</td>
                            <td>{fmt(g.error, key === "gamma" ? 6 : 4)}</td>
                            <td>
                              [
                              {g.ci95
                                .map((x) => fmt(x, key === "gamma" ? 6 : 4))
                                .join(", ")}
                              ]
                            </td>
                          </tr>
                        );
                      }),
                    )}
                  </tbody>
                </table>
              </div>
              <details className="mt-4">
                <summary>Gamma bump stability, martingale and runtime</summary>
                {mc.data.rows.map((row) => (
                  <div key={row.model} className="my-3 text-sm">
                    <p>
                      {row.model}: gamma{" "}
                      {row.gamma_bumps
                        .map(
                          (g) =>
                            `${fmt(g.spot_bump_usd, 3)} USD bump → ${fmt(g.value, 6)} ± ${fmt(1.96 * g.se, 6)}`,
                        )
                        .join("; ")}
                    </p>
                    <p>
                      Discounted spot {fmt(row.discounted_spot.value, 3)} versus
                      target {fmt(row.martingale_target, 3)} ·{" "}
                      {fmt(row.elapsed_ms, 1)} ms including simulation/Greek
                      checks.
                    </p>
                  </div>
                ))}
              </details>
              <details className="mt-4">
                <summary>Saved MC assumptions</summary>
                <pre
                  tabIndex={0}
                  className="max-h-64 overflow-auto text-xs"
                  aria-label="Saved Monte Carlo configuration"
                >
                  {JSON.stringify(mc.data.config, null, 2)}
                </pre>
              </details>
              <Evidence value={mc.data.provenance} />
            </>
          ) : null}
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <label className="text-sm">
              Saved MC run ID
              <input
                aria-label="Saved MC run ID"
                value={mc.savedId}
                onChange={(e) => mc.setSavedId(e.target.value)}
                className="mt-1 block max-w-full rounded border border-slate-300 p-2"
              />
            </label>
            <Action
              disabled={!mc.savedId || mc.busy}
              onClick={() => mc.load(mc.savedId)}
            >
              Load saved MC run
            </Action>
          </div>
        </div>
      </section>
    </div>
  );
}
