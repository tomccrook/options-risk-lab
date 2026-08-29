import { portfolioSchema, useService } from "./api";
import { Evidence, fmt, NumberControl, Status, Action, cn } from "./components";
import type { Controls } from "./Explorer";
import { request, type Settings } from "./workbench";
export default function Portfolio({
  controls,
  settings,
  setSettings,
}: {
  controls: Controls;
  settings: Settings;
  setSettings: (s: Settings) => void;
}) {
  const result = useService(
    "/api/portfolio",
    request(controls, settings),
    portfolioSchema,
  );
  return (
    <div className="grid gap-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="space-y-5">
        <h2 className="text-lg font-semibold">Stress the book</h2>
        <p className="text-sm text-slate-600">
          Deterministic synthetic stresses. Compare marks before funding or
          execution.
        </p>
        <NumberControl
          label="Spot shock"
          value={settings.spotShock}
          onChange={(x) => setSettings({ ...settings, spotShock: x })}
          min={-40}
          max={40}
          unit="%"
        />
        <NumberControl
          label="IV level shock"
          value={settings.volShock}
          onChange={(x) => setSettings({ ...settings, volShock: x })}
          min={-10}
          max={20}
          unit="vol points"
          step={0.5}
        />
        <NumberControl
          label="Advance time"
          value={settings.horizon}
          onChange={(x) => setSettings({ ...settings, horizon: x })}
          min={0}
          max={365}
          unit="calendar days"
        />
        <Action
          onClick={() =>
            setSettings({
              ...settings,
              case: "delta-hedged-straddle",
              spotShock: 20,
              volShock: 5,
              horizon: 30,
            })
          }
        >
          Load adverse straddle
        </Action>
      </aside>
      <section className="min-w-0">
        <h2 className="text-2xl font-semibold">
          Local neutrality, global loss
        </h2>
        <p className="mt-2 mb-6 text-sm text-slate-600">
          Full repricing uses each contract's expiry and the selected surface
          rule. Partial Greeks hold assigned IV fixed.
        </p>
        <Status {...result} />
        {result.data ? (
          <>
            <div
              tabIndex={0}
              role="region"
              aria-label="Signed position inventory"
              className="overflow-x-auto"
            >
              <table className="w-full text-sm tabular-nums">
                <caption className="text-left font-medium">
                  Signed positions · {settings.case} · multiplier applied once
                </caption>
                <thead>
                  <tr>
                    <th>ID / type</th>
                    <th>Qty</th>
                    <th>Strike</th>
                    <th>Days</th>
                    <th>IV %</th>
                    <th>Value USD</th>
                    <th>Delta shares</th>
                  </tr>
                </thead>
                <tbody>
                  {result.data.risk.positions.map((p) => (
                    <tr key={p.id}>
                      <th scope="row">
                        {p.id} / {p.kind}
                      </th>
                      <td>{fmt(p.quantity, 2)}</td>
                      <td>{fmt(p.strike, 2)}</td>
                      <td>{fmt(p.days, 0)}</td>
                      <td>{fmt(p.assigned_iv * 100, 2)}</td>
                      <td>{fmt(p.price, 2)}</td>
                      <td>{fmt(p.delta, 2)}</td>
                    </tr>
                  ))}
                  <tr>
                    <th scope="row">Shares / cash</th>
                    <td>{fmt(result.data.risk.shares, 0)}</td>
                    <td colSpan={3}>Cash {fmt(result.data.risk.cash, 2)}</td>
                    <td colSpan={2}>NAV {fmt(result.data.risk.nav, 2)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div
              tabIndex={0}
              role="region"
              aria-label="Gross and net exposures"
              className="my-6 overflow-x-auto"
            >
              <table className="w-full text-sm tabular-nums">
                <caption className="text-left font-medium">
                  Risk cancellation does not erase gross inventory
                </caption>
                <thead>
                  <tr>
                    <th>Exposure</th>
                    <th>Net</th>
                    <th>Gross</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ["delta", "Share-equivalent delta"],
                    ["gamma", "Gamma / USD"],
                    ["vega", "Vega / decimal IV"],
                  ].map(([key, label]) => (
                    <tr key={key}>
                      <th scope="row">{label}</th>
                      <td>{fmt(result.data?.risk.net[key])}</td>
                      <td>{fmt(result.data?.risk.gross[key])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-xs text-slate-600">
                Surface-aware total delta{" "}
                {fmt(result.data.risk.total_surface_delta, 2)} shares ·
                return-scale gamma {fmt(result.data.risk.return_scale_gamma, 2)}{" "}
                USD · vega / vol point{" "}
                {fmt(result.data.risk.vega_per_vol_point, 2)} USD
              </p>
            </div>
            <div className="border-l-4 border-teal-700 bg-white p-5">
              <h3 className="font-semibold">
                Selected stress: {settings.spotShock}% spot, {settings.volShock}{" "}
                vol points, {settings.horizon} days
              </h3>
              <dl className="mt-4 grid gap-4 sm:grid-cols-3 tabular-nums">
                <div>
                  <dt className="text-sm text-slate-600">Full mark change</dt>
                  <dd
                    className="mt-1 text-2xl font-medium"
                    data-testid="full-change"
                  >
                    {fmt(result.data.selected.full_change, 2)} USD
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-slate-600">
                    Taylor approximation
                  </dt>
                  <dd className="mt-1 text-2xl font-medium">
                    {fmt(result.data.selected.approximation, 2)} USD
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-slate-600">
                    Unexplained residual
                  </dt>
                  <dd
                    className="mt-1 text-2xl font-medium"
                    data-testid="residual"
                  >
                    {fmt(result.data.selected.residual, 2)} USD
                  </dd>
                </div>
              </dl>
              <p className="mt-4 text-sm text-slate-600">
                Option change {fmt(result.data.selected.option_change, 2)} +
                shares {fmt(result.data.selected.share_change, 2)}. Cash
                funding, dividends and fills enter the financed hedge and replay
                views.
              </p>
              <details className="mt-3 text-sm">
                <summary>Taylor terms and omitted effects</summary>
                <p className="mt-2">
                  {Object.entries(result.data.selected.terms)
                    .map(([k, v]) => `${k}: ${fmt(v, 2)} USD`)
                    .join(" · ")}
                  . Rate/carry/time cross terms and higher orders omitted;
                  residual retained.
                </p>
              </details>
            </div>
            <div
              tabIndex={0}
              role="region"
              aria-label="Scenario grid"
              className="mt-6 overflow-x-auto"
            >
              <table className="w-full text-sm tabular-nums">
                <caption className="text-left font-medium">
                  Full mark-change heatmap (USD) · select a cell ·{" "}
                  {settings.horizon} days
                </caption>
                <thead>
                  <tr>
                    <th>Spot shock / IV change</th>
                    {[-5, 0, 5].map((v) => (
                      <th key={v}>
                        {v > 0 ? "+" : ""}
                        {v} vol points
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[-20, -10, 0, 10, 20].map((s) => (
                    <tr key={s}>
                      <th scope="row">
                        {s > 0 ? "+" : ""}
                        {s}%
                      </th>
                      {result.data?.grid
                        .filter(
                          (r) => Math.round(r.shock.spot_return * 100) === s,
                        )
                        .map((r, i) => (
                          <td
                            key={i}
                            className={cn(
                              r.full_change < 0 ? "bg-slate-100" : "bg-teal-50",
                            )}
                          >
                            <Action
                              onClick={() =>
                                setSettings({
                                  ...settings,
                                  spotShock: s,
                                  volShock: r.shock.vol_change * 100,
                                })
                              }
                            >
                              {fmt(r.full_change, 2)}
                            </Action>
                          </td>
                        ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Evidence value={result.data.provenance} />
          </>
        ) : null}
      </section>
    </div>
  );
}
