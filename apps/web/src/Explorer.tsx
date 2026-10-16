import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from "recharts";
import { curveSchema, useService, type Greeks } from "./api";
import { Evidence, fmt, NumberControl, Status } from "./components";
export type Controls = {
  spot: number;
  strike: number;
  vol: number;
  days: number;
  rate: number;
  yield_: number;
};
export const market = (c: Controls) => ({
  spot: c.spot,
  vol: c.vol / 100,
  rate: c.rate / 100,
  yield_: c.yield_ / 100,
  valuation_time: "2026-10-04T00:00:00Z",
});
export const option = (c: Controls, kind = "call", id = "call-100") => ({
  id,
  strike: c.strike,
  kind,
  expiry: new Date(Date.UTC(2026, 9, 4) + c.days * 86400000).toISOString(),
  multiplier: 100,
});
const units = {
  price: "USD / share",
  delta: "share-equivalent / option share",
  gamma: "1 / USD",
  vega: "USD / decimal IV",
  theta: "USD / calendar year",
  rho: "USD / decimal rate",
  vanna: "1 / decimal IV",
  volga: "USD / decimal IV²",
};
export default function Explorer({
  controls,
  setControls,
  motion = "flat",
}: {
  controls: Controls;
  setControls: (c: Controls) => void;
  motion?: "flat" | "frozen-strike" | "sticky-log-moneyness";
}) {
  const [greek, setGreek] = useState<Exclude<keyof Greeks, "quality">>("delta");
  const [axis, setAxis] = useState<"spot" | "vol" | "days">("spot");
  const [basis, setBasis] = useState("per-share");
  const [quantity, setQuantity] = useState(-1);
  const signed = basis === "signed-contracts";
  const chartUnits = signed
    ? {
        ...units,
        price: "USD",
        delta: "shares",
        gamma: "shares / USD",
        vanna: "shares / decimal IV",
      }
    : units;
  const config = {
    basis,
    quantity,
    market: market(controls),
    option: option(controls),
    axis,
    surface: { motion },
    low: axis === "spot" ? 50 : axis === "vol" ? 0.05 : 1,
    high: axis === "spot" ? 150 : axis === "vol" ? 0.6 : 730,
  };
  const result = useService("/api/curves", config, curveSchema);
  const rows = result.data?.rows.map((r) => ({
    x: r.x,
    call: r.call[greek],
    put: r.put[greek],
  }));
  return (
    <div className="grid gap-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="space-y-5">
        <h2 className="text-lg font-semibold">Matched contracts</h2>
        <p className="text-sm text-slate-600">
          Matched European call and put. Fixed strike, same expiry and assigned
          IV. Curve motion follows the active surface rule; Greeks are partial
          at each point.
        </p>
        <label className="block text-sm font-medium">
          Exposure basis
          <select
            aria-label="Exposure basis"
            value={basis}
            onChange={(e) => setBasis(e.target.value)}
            className="mt-2 w-full rounded border border-slate-300 p-2"
          >
            <option value="per-share">Long per option share</option>
            <option value="signed-contracts">Signed contracts × 100</option>
          </select>
        </label>
        {signed ? (
          <NumberControl
            label="Signed contracts"
            value={quantity}
            min={-10}
            max={10}
            onChange={setQuantity}
          />
        ) : null}
        {(
          [
            ["Spot", "spot", 20, 250, 1, "USD"],
            ["Strike", "strike", 30, 200, 1, "USD"],
            ["Volatility", "vol", 1, 100, 0.5, "% annual"],
            ["Maturity", "days", 1, 730, 1, "calendar days"],
            ["Rate", "rate", -5, 15, 0.25, "% annual"],
            ["Continuous yield", "yield_", 0, 10, 0.25, "% annual"],
          ] as const
        ).map(([label, key, min, max, step, unit]) => (
          <NumberControl
            key={key}
            label={label}
            value={controls[key]}
            min={min}
            max={max}
            step={step}
            unit={unit}
            onChange={(v) => setControls({ ...controls, [key]: v })}
          />
        ))}
      </aside>
      <section className="min-w-0">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold">
              Local risk, across the curve
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              Call and put share gamma and vega under these matched European
              assumptions.
            </p>
          </div>
          <div className="flex gap-3">
            <label className="text-sm">
              Measure
              <select
                aria-label="Greek measure"
                value={greek}
                onChange={(e) => setGreek(e.target.value as typeof greek)}
                className="ml-2 rounded border border-slate-300 p-2"
              >
                {Object.keys(units).map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              Sweep
              <select
                aria-label="Sweep axis"
                value={axis}
                onChange={(e) => setAxis(e.target.value as typeof axis)}
                className="ml-2 rounded border border-slate-300 p-2"
              >
                <option value="spot">Spot</option>
                <option value="vol">Decimal IV</option>
                <option value="days">Calendar days</option>
              </select>
            </label>
          </div>
        </div>
        <Status {...result} />
        {result.data ? (
          <>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="mb-4 text-sm font-medium">
                {greek} · {chartUnits[greek]}
              </p>
              <div
                className="h-80"
                role="img"
                aria-label={`Matched call and put ${greek} versus ${axis}; exact selected values in table below`}
              >
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={rows}
                    margin={{ top: 12, right: 24, left: 16, bottom: 28 }}
                    accessibilityLayer
                  >
                    <CartesianGrid stroke="#e2e8f0" vertical={false} />
                    <XAxis
                      dataKey="x"
                      type="number"
                      domain={["dataMin", "dataMax"]}
                      label={{
                        value:
                          axis === "spot"
                            ? "Spot (USD)"
                            : axis === "vol"
                              ? "IV (decimal annual)"
                              : "Remaining calendar days",
                        position: "bottom",
                        offset: 8,
                      }}
                      tickFormatter={(v) => fmt(v, axis === "vol" ? 2 : 0)}
                    />
                    <YAxis
                      width={65}
                      tickFormatter={(v) => fmt(v, greek === "gamma" ? 3 : 2)}
                    />
                    <Tooltip
                      formatter={(v) => fmt(typeof v === "number" ? v : null)}
                    />
                    <Legend verticalAlign="top" />
                    <ReferenceLine y={0} stroke="#64748b" />
                    <ReferenceLine
                      x={
                        axis === "spot"
                          ? controls.spot
                          : axis === "vol"
                            ? controls.vol / 100
                            : controls.days
                      }
                      stroke="#64748b"
                      strokeDasharray="3 3"
                    />
                    <Line
                      dataKey="call"
                      name="Call · solid"
                      stroke="#0f766e"
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      dataKey="put"
                      name="Put · dashed"
                      stroke="#334155"
                      strokeDasharray="6 4"
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div
              tabIndex={0}
              role="region"
              aria-label="Selected analytical Greeks"
              className="overflow-x-auto"
            >
              <table className="mt-6 w-full text-sm tabular-nums">
                <caption className="mb-3 text-left font-medium">
                  Selected spot {fmt(controls.spot, 2)} ·{" "}
                  {signed
                    ? `${quantity} contracts × 100`
                    : "long per-share values"}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Contract</th>
                    <th scope="col">Price {signed ? "USD" : "USD/share"}</th>
                    <th scope="col">Delta</th>
                    <th scope="col">Gamma {signed ? "shares/USD" : "1/USD"}</th>
                    <th scope="col">Vega / 1 vol point</th>
                  </tr>
                </thead>
                <tbody>
                  {(["call", "put"] as const).map((k) => (
                    <tr key={k}>
                      <th scope="row" className="capitalize">
                        {k}
                      </th>
                      <td data-testid={`${k}-price`}>
                        {fmt(result.data?.selected[k].price)}
                      </td>
                      <td>{fmt(result.data?.selected[k].delta)}</td>
                      <td>{fmt(result.data?.selected[k].gamma, 6)}</td>
                      <td>
                        {fmt(
                          result.data?.selected[k].vega == null
                            ? null
                            : result.data.selected[k].vega * 0.01,
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-slate-600">
              Multiply by signed quantity × contract multiplier to obtain book
              exposures. Gamma enters Taylor P&L as ½ΓΔS². Undefined kink values
              remain missing.
            </p>
            {(axis === "spot" && (controls.spot < 50 || controls.spot > 150)) ||
            (axis === "vol" && (controls.vol < 5 || controls.vol > 60)) ? (
              <p role="status" className="mt-3 text-sm">
                Selected state lies outside the plotted sweep; the table still
                prices the selected state.
              </p>
            ) : null}
            <Evidence value={result.data.provenance} />
          </>
        ) : null}
      </section>
    </div>
  );
}
