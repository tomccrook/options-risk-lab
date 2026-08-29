import { useState } from "react";
import {
  CartesianGrid,
  ScatterChart,
  Scatter,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  workbenchConfigSchema,
  comparisonSchema,
  useService,
  submit,
  jobSchema,
  type Comparison,
} from "./api";
import { Action, Evidence, fmt, NumberControl, Status } from "./components";
import type { Controls } from "./Explorer";
import { request, type Settings } from "./workbench";
export default function Hedges({
  controls,
  settings,
  setSettings,
}: {
  controls: Controls;
  settings: Settings;
  setSettings: (s: Settings) => void;
}) {
  const config = request(controls, settings);
  const current = useService("/api/hedges", config, comparisonSchema);
  const [selected, setSelected] = useState("Scenario CVaR");
  const [saved, setSaved] = useState<Comparison>();
  const [id, setId] = useState("");
  const [message, setMessage] = useState("");
  const data = saved ?? current.data;
  const savedInputs = saved
    ? workbenchConfigSchema.parse(saved.config)
    : undefined;
  const chosen = data?.hedges.find((h) => h.name === selected);
  async function save() {
    try {
      const run = await submit("/api/comparisons", config);
      setId(run);
      localStorage.setItem("orl:comparison:v1", run);
      setMessage(`Saved comparison ${run}. Original assumptions retained.`);
    } catch (e) {
      setMessage(String(e));
    }
  }
  async function restore() {
    try {
      const run = id || localStorage.getItem("orl:comparison:v1");
      if (!run) throw new Error("Save a comparison first");
      const job = jobSchema.parse(
        await (await fetch(`/api/jobs/${run}`)).json(),
      );
      if (job.status !== "complete")
        throw new Error(
          `Run ${job.status}: ${job.error ?? "check again shortly"}`,
        );
      setSaved(comparisonSchema.parse(job.result));
      setMessage(`Showing saved run ${run} with its original configuration.`);
    } catch (e) {
      setMessage(String(e));
    }
  }
  return (
    <div className="grid gap-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="space-y-5">
        <h2 className="text-lg font-semibold">Feasible inventory</h2>
        <NumberControl
          label="Round-trip cost budget"
          value={settings.budget}
          onChange={(x) => {
            setSaved(undefined);
            setSettings({ ...settings, budget: x });
          }}
          min={0}
          max={200}
          unit="USD"
        />
        <NumberControl
          label="Gross capital limit"
          value={settings.capital}
          onChange={(x) => {
            setSaved(undefined);
            setSettings({ ...settings, capital: x });
          }}
          min={0}
          max={25000}
          step={500}
          unit="USD"
        />
        <NumberControl
          label="Share half-spread"
          value={settings.spread}
          onChange={(x) => {
            setSaved(undefined);
            setSettings({ ...settings, spread: x });
          }}
          min={0}
          max={0.2}
          step={0.01}
          unit="USD/share"
        />
        <p className="text-xs text-slate-600">
          Options: integer ±3 contracts, multiplier 100, half-spread
          $0.05/share, $0.50 fee/contract per fill. Shares integer ±250. Gross
          capital is a research limit, not exchange margin.
        </p>
        <Action onClick={save} disabled={current.pending}>
          Save comparison
        </Action>
        <label className="block text-sm">
          Saved run ID
          <input
            aria-label="Saved run ID"
            value={id}
            onChange={(e) => setId(e.target.value)}
            className="mt-2 w-full rounded border border-slate-300 p-2 font-mono text-xs"
          />
        </label>
        <Action onClick={restore}>Load saved comparison</Action>
        {saved ? (
          <Action onClick={() => setSaved(undefined)}>
            Return to current assumptions
          </Action>
        ) : null}
        <p role="status" className="break-all text-sm text-slate-600">
          {message}
        </p>
      </aside>
      <section className="min-w-0">
        <h2 className="text-2xl font-semibold">
          Pay for the hedge, inspect the residual
        </h2>
        <p className="my-3 text-sm text-slate-600">
          Conditional weighted 95% stress CVaR, uniform 15-state grid,{" "}
          {savedInputs?.selected_shock.days ?? settings.horizon}-day horizon.
          This is not a market tail forecast.
        </p>
        {saved ? (
          <p className="my-4 rounded bg-teal-50 p-3 text-teal-900">
            Saved snapshot · calculations use the original run's inputs.
            Original cost budget: ${savedInputs?.limits.cost_budget}; capital: $
            {savedInputs?.limits.capital_budget}; surface:{" "}
            {savedInputs?.surface.motion}.
          </p>
        ) : (
          <Status {...current} />
        )}{" "}
        {data ? (
          <>
            <div
              className="h-64 rounded-lg border border-slate-200 bg-white p-4"
              role="img"
              aria-label="Hedge cost versus conditional stress CVaR. Exact values and feasibility in the comparison table."
            >
              <ResponsiveContainer>
                <ScatterChart
                  margin={{ top: 15, right: 30, left: 20, bottom: 25 }}
                  accessibilityLayer
                >
                  <CartesianGrid stroke="#e2e8f0" />
                  <XAxis
                    type="number"
                    dataKey="cost"
                    name="Round-trip cost"
                    unit=" USD"
                    label={{
                      value: "Round-trip execution cost (USD)",
                      position: "bottom",
                      offset: 5,
                    }}
                  />
                  <YAxis
                    type="number"
                    dataKey="cvar"
                    name="Conditional CVaR"
                    label={{
                      value: "CVaR (USD)",
                      angle: -90,
                      position: "insideLeft",
                    }}
                  />
                  <Tooltip cursor={{ strokeDasharray: "3 3" }} />
                  <Scatter
                    name="Feasible integer frontier"
                    data={data.frontier}
                    fill="#0f766e"
                    isAnimationActive={false}
                  />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
            <div
              tabIndex={0}
              role="region"
              aria-label="Compared hedge methods"
              className="mt-6 overflow-x-auto"
            >
              <table className="w-full text-sm tabular-nums">
                <caption className="text-left font-medium">
                  Executed integer alternatives · choose one to inspect trades
                </caption>
                <thead>
                  <tr>
                    <th>Hedge</th>
                    <th>Status</th>
                    <th>Cost USD</th>
                    <th>Capital USD</th>
                    <th>CVaR USD</th>
                    <th>Worst loss USD</th>
                  </tr>
                </thead>
                <tbody>
                  {data.hedges.map((h) => (
                    <tr key={h.name}>
                      <th scope="row">
                        <Action onClick={() => setSelected(h.name)}>
                          {h.name}
                        </Action>
                      </th>
                      <td>{h.status}</td>
                      <td>{fmt(h.cost, 2)}</td>
                      <td>{fmt(h.capital, 2)}</td>
                      <td>{fmt(h.cvar, 2)}</td>
                      <td>{fmt(h.worst_loss, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3 className="mt-7 text-lg font-semibold">
              {chosen?.name} · actual additional trades
            </h3>
            {chosen?.trades ? (
              <>
                <div
                  tabIndex={0}
                  role="region"
                  aria-label="Selected executed trades"
                  className="overflow-x-auto"
                >
                  <table className="mt-3 w-full text-sm tabular-nums">
                    <thead>
                      <tr>
                        <th>Instrument</th>
                        <th>Signed quantity</th>
                        <th>Mid USD/share</th>
                        <th>Multiplier</th>
                      </tr>
                    </thead>
                    <tbody>
                      {chosen.trades.map((t) => (
                        <tr key={t.id}>
                          <th scope="row">{t.id}</th>
                          <td>{fmt(t.quantity, 0)}</td>
                          <td>{fmt(t.mid, 4)}</td>
                          <td>{t.multiplier}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-4 text-sm">
                  Residual delta {fmt(chosen.residual?.delta, 2)} shares · gamma{" "}
                  {fmt(chosen.residual?.gamma, 4)} /USD · vega{" "}
                  {fmt(chosen.residual?.vega, 2)} /decimal IV.
                </p>
                <p className="mt-2 text-xs text-slate-600">
                  Fractional control:{" "}
                  {chosen.fractional_control
                    ?.map((x) => fmt(x, 3))
                    .join(", ") ?? "not used"}{" "}
                  · all reported cost/risk re-evaluated after integer rounding.
                  Normalized system condition {fmt(data.condition, 1)}.
                </p>
              </>
            ) : (
              <p className="mt-3">
                No executable recommendation: {chosen?.status}
              </p>
            )}
            <p className="mt-4 text-xs text-slate-600">
              {data.basis}. Existing book retained at horizon marks; only added
              hedges close out. Funding-adjusted execution cost{" "}
              {fmt(chosen?.financed_cost, 2)} USD. Surface{" "}
              {savedInputs?.surface.motion ?? settings.motion}; no artificial
              certainty score.
            </p>
            <Evidence value={data.provenance} />
          </>
        ) : null}
      </section>
    </div>
  );
}
