# Assumptions register

Owner: Tom Crook. Review date: 2026-10-04. All default data synthetic; no market-return claims.

| ID | Assumption | Consequence / challenge |
|---|---|---|
| A01 | Single SYNTH equity; USD, European cash settlement, multiplier 100 | American exercise/assignment and multi-factor trading rejected |
| A02 | UTC aware valuation/expiry, ACT/365 calendar maturity | Return generator uses same year fractions; trading frequency separately stated |
| A03 | Constant continuously compounded r/q, decimal annual IV | No discrete dividends; negative rates allowed in bounded domain |
| A04 | Prices per share; delta share-equivalent; vega decimal and ×0.01 per vol point | Signed quantities and multipliers applied once |
| A05 | Theta advances valuation time; partial Greeks freeze assigned IV | Surface-aware finite spot bumps reported separately |
| A06 | Expiry/deterministic payoff kink derivatives unavailable | No invented smooth expiry gamma; UI shows undefined. Scenarios beyond any open expiry reject because the earlier settlement spot/path is unknown |
| A07 | Synthetic level+skew log(K/F)+term IV; frozen-strike or sticky-log-moneyness motion | Smooth specification is not an arbitrage-free calibration; invalid vols reject |
| A08 | Costs in execution price plus explicit fee exactly once | Received option premium offset by signed liability; funding benchmark separate |
| A09 | Shares have integer granularity; static hedge options integer | Rounded result fully re-evaluated; no fractional optimum claim |
| A10 | Static stress CVaR uses declared weighted synthetic states | Conditional stress objective, not estimated market tail probability |
| A11 | Causal decision at node; delayed request executes at later node quote | Decision target may be stale; no future state passed to policy |
| A12 | RN GBM control drift r−q; physical drift/misspecification/jumps separately named | Mean P&L does not establish trading alpha |
| A13 | American FD constant-carry put is pricing/risk only | No traded lifecycle claim; mesh/bump uncertainty part of label eligibility |
| A14 | ML smooth tanh, float64 CPU; dimensionless P/K inputs; matched epochs/data/seeds | Device results may differ; no silent GPU fallback |
| A15 | Actual host macOS arm64; Windows/RTX not accessible in this session | Windows commands supplied; Windows execution and CUDA performance unverified |
| A16 | Local files/results only; optional entitled data/cloud/native disabled | Real-data adapter needs contract/timing/usage audit; cloud needs spending budget |

## Model-risk extension (registered before results)

| ID | Assumption | Consequence / challenge |
|---|---|---|
| A17 | BSM, Merton jump-diffusion and Heston are separate risk-neutral synthetic models; Monte Carlo is an engine | Distinguish model disagreement, quadrature/mixture error, sampling uncertainty and discretisation bias |
| A18 | Merton log jumps normal; drift includes −lambda*(E[J]−1); Heston QE with martingale correction | Exact terminal Merton sampling; Heston requires step convergence and nonnegative variance checks |
| A19 | Optional one-point premium matching adjusts Merton diffusion sigma and Heston v0=theta, with other parameters fixed | Same initial European premium; no real-market surface calibration or forecast claim |
| A20 | Heston current variance is an idealised observable available to every hedger; parameters fixed before replay | No information advantage from future variance; actual latent-variance estimation is outside this synthetic control |
| A21 | Replay option marks/entry premiums come from a common generator model; hedgers only change share targets | Premium cannot inflate P&L; stock-only Heston hedges retain independent volatility risk and Merton jump risk |
| A22 | Heston vega0 is dV/dsqrt(current variance), holding theta/kappa/xi/rho fixed | Distinct from BSM/Merton diffusion vega and an implied-volatility surface shock |

| A23 | Extension has126 equal ACT/365 decision nodes/year; shared policy identifiers daily/weekly mean every1/5nodes | Disclose actual calendar spacing (~2.90/14.48days for1year); no literal daily/weekly execution claim |

Thin-time-value premium matching (<$0.005) is poorly identified and rejects. Model replay rejects either option entry bid below zero under the declared5c half-spread; no infeasible synthetic quote is silently traded. These boundary guards leave the frozen ATM study unchanged.
