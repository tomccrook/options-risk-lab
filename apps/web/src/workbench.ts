import { market, option, type Controls } from "./Explorer";
export type Settings = {
  case: string;
  motion: "flat" | "frozen-strike" | "sticky-log-moneyness";
  spotShock: number;
  volShock: number;
  horizon: number;
  budget: number;
  capital: number;
  spread: number;
};
export function request(c: Controls, s: Settings) {
  return {
    market: market(c),
    option: option(c),
    case: s.case,
    surface: { motion: s.motion },
    selected_shock: {
      spot_return: s.spotShock / 100,
      vol_change: s.volShock / 100,
      days: s.horizon,
    },
    shocks: [-0.2, -0.1, 0, 0.1, 0.2].flatMap((spot_return) =>
      [-0.05, 0, 0.05].map((vol_change) => ({
        spot_return,
        vol_change,
        days: s.horizon,
      })),
    ),
    limits: {
      cost_budget: s.budget,
      capital_budget: s.capital,
      share_half_spread: s.spread,
    },
  };
}
