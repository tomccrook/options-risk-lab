# Options Risk and Hedging Laboratory — research report

Tom Crook · MSc Computational Finance · 4 October 2026. Synthetic research for quantitative trading/research interviews. No observed market data or profitability inference.

## Question and evidence boundary

When apparently hedged local Greeks leave meaningful losses, which feasible hedges reduce those losses after costs? The study connects matched European call/put Greeks to signed book risk, full scenario repricing, actual hedge trades and financed causal replay. It distinguishes a finite mark change from terminal financed error and retains losses and failed hypotheses.

Core trading scope is one SYNTH equity, USD, European cash settlement, multiplier 100, continuous r/q, UTC ACT365. American puts are a separate numerical/ML track. All quotes, spreads, paths and candidate contracts are synthetic. These are conditional calculations, with no alpha claim.

European controls independently reconcile call 10.4505835722, put 5.5735260223, call delta .6368306512, gamma .01876201735, decimal vega 37.5240346917 at S=K=100, tau=1, r=.05, q=0, sigma=.20. QuantLib analytical prices and first Greeks agree over an additional carry/rate grid; finite bumps check mixed/higher derivatives. Expiry/deterministic payoff kinks return unavailable sensitivities. Prices use signed quantity × multiplier once.

## Ordinary and adverse auditable cases

The default book shorts one call and one put and holds 27 shares. It has initial NAV $10,000; option liability $1,602.41, shares $2,700 and cash $8,902.41. Received premium is offset by liability. Partial delta is -0.3661 shares, gamma -3.752403 shares/USD and vega -75.05 USD/vol point.

A small +1% spot/+0.25 vol point/1.5-calendar-day state has full mark change $-17.43; Taylor $-17.55; residual $0.12. For the +20% spot/+5 vol point/30-calendar-day adverse state, option change is $-1,311.07, share change $540.00, full change $-771.07, Taylor $-1,012.88, and full-minus-Taylor residual $241.81. Gamma, vega and mixed/time effects explain why near-zero delta is insufficient.

The ideal fractional locally-matched control has partial delta/gamma/vega essentially zero. Under the same large positive stress it still loses $34.69; its residual is $-2.48. Remaining theta/vanna/volga and finite-state variation matter. This is an ideal control, not an integer executable book. The residual is omitted higher/time/carry terms and curvature, not an accounting error.



## Feasible paid static hedges

Candidate near put: K95, 180 calendar days, modeled mid $2.5051356955/share. Far call: K105, 730 days, mid $13.6396150968/share. Integer additions bounded ±3 contracts and ±250 shares. Half-spreads: stock $0.01/share, option $0.05/share; option fee $0.50/contract on entry and exit. Gross capital: absolute stock notional + gross option premium/liability + entry costs, limit $10,000. This is a research limit, not exchange margin or borrow availability.

The objective integrates exact worst 5% mass over 15 uniform synthetic stresses, ±20/10/0% spot × ±5/0 vol points at 30 days. Here each state's mass exceeds 5%, so CVaR equals worst loss. Original book retained at horizon marks; added hedges enter and close at modeled bid/ask. Funding, carry, premium outlay and execution costs enter once. It is not a forecast of market ES.

| Method | Additional shares / put / call | Costs USD | Gross capital USD | Conditional CVaR95 USD |
|---|---|---|---|---|
| No additional hedge | [0.0, 0.0, 0.0] | 0.00 | 0.00 | 1,049.98 |
| Underlying delta | [0.0, 0.0, 0.0] | 0.00 | 0.00 | 1,049.98 |
| Local delta/gamma | [54.0, 2.0, 0.0] | 23.08 | 5,912.57 | 186.76 |
| Local delta/gamma/vega | [-35.0, 1.0, 1.0] | 22.70 | 5,125.83 | 101.49 |
| Scenario CVaR | [-33, 1, 1] | 22.66 | 4,925.81 | 72.30 |

The scenario choice sells 33 additional shares and buys one of each candidate. Final stock holding is −6 shares. Its cost $22.66 is slightly below the rounded D/G/V baseline; CVaR is 28.8% lower in these states. Residual delta is +2.2191 shares: matching local delta exactly was not optimal for this support. The normalized local system condition is 59,006.3; rank/condition failures reject. Fractional solutions are reported as controls and integer outcomes fully repriced.

Exact enumeration also produces a nondominated cost/CVaR frontier. At a zero cost budget, the paid optimum is no additions. A $25 budget already admits the default optimum; $100 adds no benefit. Narrowing spot support to ±10/5/0% changes the chosen shares to −36 and conditional CVaR to $41.12. This support sensitivity prevents a universal hedge recommendation. It is an explanatory post-lock static experiment, not strategy tuning.



## Surface-motion experiment

Both frozen-strike and sticky-log-moneyness start from identical assigned initial IV. Level/skew/term are synthetic, partial Greeks hold IV fixed, total spot delta includes the selected motion by finite bump. Repricing rolls maturity and term inputs. On the same frozen-initial book and 15 states, worst unfinanced mark loss is:

| Motion | Worst mark loss USD |
|---|---|
| flat | 1,045.46 |
| frozen-strike | 1,024.56 |
| sticky-log-moneyness | 889.82 |

H4's $10 materiality threshold is exceeded between frozen and sticky. This changes conditional stress outcomes, without providing an empirical motion estimate. Sampled strike monotonicity/convexity checks are necessary diagnostics only; no arbitrage-free calibration or maturity-calendar proof is claimed. Invalid IV/surface samples explicitly reject.

## Causal accounting and locked replay

Each decision receives current node risk, shares and pending status only. Delayed targets fill at the later quote. Funding compounds cash; continuous dividends use left-node share/spot exposure and converge as intervals shrink. Fees/spreads enter actual fills; NAV uses signed mid marks; expiry pays exact cash settlement; terminal shares liquidate with costs. Financed error is terminal NAV minus allocated $10,000 grown at r. It includes original option costs. Cash fixtures A and B reconcile to $1,006 and $9,900 respectively; an independent fee/roll fixture ends $1,011. Missing marks fail rather than remove liabilities.

The locked protocol used seeds 1009/2027/3041, 1,024 independent paths each, 252 uniform valuation nodes over 365 calendar days. “Daily/weekly/monthly” are node schedules 1/5/21, not an exchange business-day calendar. Same paths/information/costs for each policy; 10-share band fixed before testing. RN GBM matched drift r−q with sigma20%; misspecified realized sigma30% against20% pricing; jump is −20% at midpoint with one-node delay. Share bounds ±250 and gross capital $25,000 constrain decisions and actual delayed fills. Multi-expiry dynamic trading rejects; static calendars remain supported.

138,240 episode rows cover 3 regimes × 3 stock half-spreads × 3 seeds × 1,024 paths × 5 policies. There are 3,072 paths per regime/cost cell and 154 tail observations (153.6 weighted mass). Independent-path bootstrap uses 2,000 draws, preserving policy pairing. It pools independent paths across seeds; separate three-batch metrics are retained. Nodes are not sampling units. Intervals quantify Monte Carlo uncertainty conditional on each generator, not uncertainty in the market model. No policy was tuned after locked tests.

At a one-cent stock half-spread:

| Regime | Policy | RMSE USD | ES95 USD [CI] | Mean error USD [CI] | Costs USD |
|---|---|---|---|---|---|
| matched | none | 1,399.87 | 4,068.06 [3,796.65, 4,320.70] | -33.65 [-83.46, 13.77] | 10.00 |
| matched | daily | 89.09 | 224.75 [211.27, 239.42] | -19.85 [-22.96, -16.90] | 20.98 |
| matched | weekly | 195.78 | 483.03 [450.05, 515.23] | -11.55 [-18.57, -5.10] | 15.59 |
| matched | monthly | 381.95 | 895.16 [841.23, 944.99] | -2.47 [-15.96, 10.44] | 13.08 |
| matched | band | 131.20 | 304.33 [290.87, 319.07] | -16.12 [-20.72, -11.75] | 16.72 |
| misspecified | none | 2,297.70 | 7,332.63 [6,840.23, 7,795.29] | -839.84 [-914.07, -766.47] | 10.00 |
| misspecified | daily | 899.34 | 1,667.57 [1,629.03, 1,706.75] | -811.05 [-824.90, -796.97] | 23.07 |
| misspecified | weekly | 928.99 | 2,047.71 [1,971.23, 2,125.31] | -797.76 [-814.76, -782.18] | 16.52 |
| misspecified | monthly | 1,027.83 | 2,596.02 [2,484.88, 2,702.10] | -780.01 [-803.67, -757.58] | 13.56 |
| misspecified | band | 900.41 | 1,693.09 [1,654.33, 1,730.17] | -808.89 [-823.26, -795.12] | 19.09 |
| jump-delay | none | 1,260.89 | 2,848.82 [2,762.45, 2,929.90] | -291.91 [-334.16, -250.03] | 10.00 |
| jump-delay | daily | 964.59 | 1,606.12 [1,581.09, 1,631.96] | -884.28 [-897.92, -870.90] | 20.13 |
| jump-delay | weekly | 992.54 | 1,900.29 [1,858.25, 1,943.09] | -872.47 [-888.80, -855.62] | 15.63 |
| jump-delay | monthly | 1,034.91 | 2,216.57 [2,143.57, 2,289.96] | -863.99 [-884.80, -843.94] | 13.49 |
| jump-delay | band | 960.90 | 1,669.33 [1,639.82, 1,698.97] | -873.01 [-887.86, -859.55] | 16.35 |

Band minus fixed-schedule paired RMSE differences (negative favours band):

| Regime | Baseline | Difference USD | 95% CI USD |
|---|---|---|---|
| matched | daily | 42.11 | [38.80, 45.28] |
| matched | weekly | -64.58 | [-71.74, -57.94] |
| matched | monthly | -250.75 | [-262.00, -239.31] |
| misspecified | daily | 1.07 | [-4.21, 5.80] |
| misspecified | weekly | -28.58 | [-44.62, -12.88] |
| misspecified | monthly | -127.42 | [-158.13, -96.23] |
| jump-delay | daily | -3.70 | [-8.27, 1.09] |
| jump-delay | weekly | -31.64 | [-43.14, -19.79] |
| jump-delay | monthly | -74.02 | [-93.89, -54.43] |

H2 is not supported against the strongest fixed baseline in the matched model: daily has smaller RMSE, band has lower turnover/cost. Misspecified and jump-delay daily/band intervals overlap zero. Misspecification generates roughly $800 negative mean error despite frequent hedging. The jump path exposes stale targets and unhedgeable gap loss; reducing tail/error risk does not imply a higher mean than no hedge under that altered generator. Costs increase net financed error and can change preferences; the figures contain all 0/1/5-cent settings.



## Limitations and defensible next work

One underlying, modeled liquidity, fixed carry, prescribed physical/misspecified/jump regimes, discrete dividends and borrow/margin mechanics absent. Surface diagnostics limited; exact stress search small and conditional. Single-expiry replay does not implement dynamic option rolling, multi-factor correlation, traded American assignment or an exotic lifecycle. GPU, Windows runtime, LSEG observations and production deployment are unverified. No data entitlement, AWS budget or measured C++ need established; extensions remain gated. CPU synthetic research requires none of them.

To extend: register a new protocol before tuning; expand valid surface/reference probes and feasible liquidity/borrow constraints; estimate chronological real-data inputs only after contract/timing/allowed-use audit; measure local need before acceleration or paid provisioning. Retain the strongest fixed schedules and analytical reference. The ML report rejects all current surrogates for active risk.

## Evidence and reproduction

- Locked evaluation: `d8098ca0fbc9474c800f01ca43f90328`; code `852da89f675447f75ae60e687d3aa734b649012d`; source SHA `e827c5e7c8044590a49e9668ac51564dcd90c534d70f69be508f0e6104f521eb`. Manifest: `artifacts/jobs/d8098ca0fbc9474c800f01ca43f90328.manifest.json`.
- Surrogate study: `dea54b8777174042ae249128f43fb7ff`; code `66f89ec7c57e7e9aa46413b9722fa612bc89e541`; source SHA `54ea0bd1084ac9b85d715be198f30ff46810451dec99ae2dde33406c900be9db`. Manifest: `artifacts/jobs/dea54b8777174042ae249128f43fb7ff.manifest.json`.
- Scientific export / static diagnostics: `479c918af4114451ae2f62e0ad0a8e9e`; code `66f89ec7c57e7e9aa46413b9722fa612bc89e541`; source SHA `67ba116b3ded2282b3b586adf04ff4141dcb593e37890d44f9a5068a742ad973`. Manifest: `artifacts/jobs/479c918af4114451ae2f62e0ad0a8e9e.manifest.json`.

Protocol SHA `312cd60e3cb06e04827a9c8f4f4204bea018e047bfeb2c8a32be8d6e963d6ce0`. Episode payload SHA `07e058db22b6805cac69d9699230fea6df18769193263ca590f9ac9bd3164532`. Artifacts are generated and ignored in Git; manifests/results persist in the local job registry. Convenience aliases identify current runs and may be replaced. Reproduce with `uv run orl demo`, then `uv run python scripts/write_reports.py --output docs`; routine checks do not retrain. Export SVG/PNG/PDF figures and Parquet tables with `uv run orl export`. Refer to demo guide, [assumptions](assumptions.md), [experiment register](experiments.md) and [ML report](ml-report.md).
