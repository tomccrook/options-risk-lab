import { StrictMode, lazy, Suspense, useState } from "react";
import { createRoot } from "react-dom/client";
import { Tabs } from "@base-ui/react/tabs";
import type { Controls } from "./Explorer";
import type { Settings } from "./workbench";
import type { AssetModelPoint } from "./modelTypes";
import "./style.css";
const Explorer = lazy(() => import("./Explorer"));
const Portfolio = lazy(() => import("./Portfolio"));
const Hedges = lazy(() => import("./Hedges"));
const Replay = lazy(() => import("./Replay"));
const Benchmark = lazy(() => import("./Benchmark"));
function App() {
  const [surface, setSurface] = useState("explorer");
  const [modelReplay, setModelReplay] = useState(false);
  const [modelPoint, setModelPoint] = useState<AssetModelPoint>();
  const [controls, setControls] = useState<Controls>({
    spot: 100,
    strike: 100,
    vol: 20,
    days: 365,
    rate: 5,
    yield_: 0,
  });
  const [settings, setSettings] = useState<Settings>({
    case: "delta-hedged-straddle",
    motion: "flat",
    spotShock: 20,
    volShock: 5,
    horizon: 30,
    budget: 100,
    capital: 10000,
    spread: 0.01,
  });
  return (
    <>
      <a className="skip" href="#workbench">
        Skip to workbench
      </a>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-5">
          <div>
            <p className="text-sm font-medium text-teal-800">
              TOM CROOK / RESEARCH LAB 01
            </p>
            <h1 className="mt-1 text-xl font-semibold">
              Options Risk & Hedging Laboratory
            </h1>
          </div>
          <span className="rounded-full border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-medium text-teal-900">
            Synthetic · European models · CPU reference
          </span>
        </div>
      </header>
      <main id="workbench" className="mx-auto max-w-7xl px-6 py-8">
        <p className="mb-6 max-w-3xl text-slate-600">
          When local Greeks look hedged, where can the portfolio still lose?
          Trace the assumptions, the trades, and the cash.
        </p>
        <div className="mb-6 flex flex-wrap items-center gap-4 rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <label>
            Current book
            <select
              aria-label="Current book"
              value={settings.case}
              onChange={(e) =>
                setSettings({ ...settings, case: e.target.value })
              }
              className="ml-2 rounded border border-slate-300 p-2"
            >
              {[
                "long-call",
                "long-put",
                "long-straddle",
                "short-straddle",
                "delta-hedged-straddle",
                "call-vertical",
                "put-vertical",
                "calendar",
                "locally-matched",
              ].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            Surface motion
            <select
              aria-label="Surface motion"
              value={settings.motion}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  motion: e.target.value as Settings["motion"],
                })
              }
              className="ml-2 rounded border border-slate-300 p-2"
            >
              <option value="flat">Flat IV control</option>
              <option value="frozen-strike">
                Frozen strike IV / term roll
              </option>
              <option value="sticky-log-moneyness">Sticky log-moneyness</option>
            </select>
          </label>
          <p className="text-xs text-slate-600">
            Spot ${controls.spot} · strike ${controls.strike} · {controls.vol}%
            IV · {controls.days} days · r {controls.rate}% / q {controls.yield_}
            %
          </p>
        </div>
        {settings.case === "locally-matched" ? (
          <p className="mb-4 text-sm text-teal-900">
            Ideal fractional D/G/V-matched control: option quantities are not
            executable integer trades. Multi-expiry replay is unsupported.
          </p>
        ) : null}
        <Tabs.Root value={surface} onValueChange={setSurface}>
          <Tabs.List
            className="mb-8 flex flex-wrap gap-2 border-b border-slate-200 pb-3"
            aria-label="Research surfaces"
          >
            {[
              ["explorer", "Greek explorer"],
              ["portfolio", "Portfolio & scenarios"],
              ["hedges", "Hedge comparison"],
              ["replay", "Replay & evaluation"],
              ["benchmark", "Model benchmark"],
            ].map(([value, label]) => (
              <Tabs.Tab
                key={value}
                value={value}
                className="rounded-md px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 data-[active]:bg-teal-50 data-[active]:text-teal-900"
              >
                {label}
              </Tabs.Tab>
            ))}
          </Tabs.List>
          <Suspense fallback={<p role="status">Loading research surface…</p>}>
            <Tabs.Panel value="explorer">
              <Explorer
                controls={controls}
                setControls={setControls}
                motion={settings.motion}
              />
            </Tabs.Panel>
            <Tabs.Panel value="portfolio">
              <Portfolio
                controls={controls}
                settings={settings}
                setSettings={setSettings}
              />
            </Tabs.Panel>
            <Tabs.Panel value="hedges">
              <Hedges
                controls={controls}
                settings={settings}
                setSettings={setSettings}
              />
            </Tabs.Panel>
            <Tabs.Panel value="replay">
              <Replay
                controls={controls}
                settings={settings}
                modelMode={modelReplay}
                onModelModeChange={setModelReplay}
                modelPoint={modelPoint}
                onUseDefaults={() => setModelPoint(undefined)}
              />
            </Tabs.Panel>
            <Tabs.Panel value="benchmark">
              <Benchmark
                controls={controls}
                onModelReplay={(point) => {
                  setModelPoint(point);
                  setModelReplay(true);
                  setSurface("replay");
                }}
              />
            </Tabs.Panel>
          </Suspense>
        </Tabs.Root>
      </main>
      <footer className="mx-auto max-w-7xl border-t border-slate-200 px-6 py-5 text-xs text-slate-600">
        Research demonstration · USD · UTC / ACT365 · No observed market data ·
        No profitability claim
        <nav
          aria-label="Research reports"
          className="mt-3 flex flex-wrap gap-4 text-teal-800 underline"
        >
          <a href="/api/reports/research">Research report</a>
          <a href="/api/reports/ml">ML report</a>
          <a href="/api/reports/models">Model-risk report</a>
          <a href="/api/reports/interview">Interview notes</a>
        </nav>
      </footer>
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
