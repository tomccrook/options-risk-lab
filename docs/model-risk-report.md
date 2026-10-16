# Model risk and numerical-engine comparison

Owner: Tom Crook, MSc Computational Finance. Synthetic CPU evidence, 2026-10-04. Extension to the completed local laboratory; original H1–H6 protected study and ML outcomes unchanged.

The main finding is conditional: matching the initial option premium does not match risk. Under the declared Heston generator, an instantaneous minimum-variance stock hedge reduced paid financed-error RMSE versus every predeclared BSM baseline. Ordinary Heston delta did worse. Under the Merton generator, Merton delta did not beat the strongest BSM baseline. More complex pricing assumptions do not automatically produce better stock hedges.

## Models and engines

Black–Scholes–Merton assumes constant diffusion volatility. Merton jump-diffusion adds Poisson normal log jumps; it is distinct from the Black–Scholes–Merton name. Heston makes instantaneous variance stochastic, mean reverting and correlated with spot. Monte Carlo is an engine for any of these models, not a fourth asset model.

All inputs are synthetic risk-neutral parameters, with continuous r/q, European cash settlement, USD and ACT/365 calendar time. No market calibration, forecast, historical backtest, real-data entitlement or American assignment lifecycle is asserted. Mac CPU verified; Windows/RTX remains unverified.

BSM's analytical formula is the numerical control. Merton uses a Poisson mixture with stock-numeraire weights and an explicit tail below 1e-14, checked against independent characteristic-function inversion. Installed QuantLib 1.43 Python does not expose JumpDiffusionEngine; this is documented rather than inventing an API. Heston uses stable affine characteristic-function inversion with a BSM control variate, analytic spot derivatives, and initial-variance sensitivity. Composite Gaussian orders 32/64 are compared; difficult points use adaptive quadrature or fail explicitly. Independent QuantLib analytic Heston 192 prices and spot/variance bumps validate the selected grid. At xi=0, a deterministic-variance BSM control and QuantLib European engine supply the limit; no division by zero.

Merton simulation includes the compensated risk-neutral drift `r−q−lambda*(E[J]−1)`, exact lognormal diffusion and Poisson-normal jumps. Heston simulation uses Andersen's quadratic-exponential variance branches plus the conditional MGF martingale correction. Variance remains nonnegative by construction; undefined correction domains reject rather than silently clipping variance or Greeks. QE discretisation bias is measured separately from sampling uncertainty.

## One-point premium matching

The anchor contract is S=K=100, tau=1 year, r=5%, q=0, base BSM sigma=20%. Fixed jump parameters are lambda=0.4/year, log-mean=−0.08, log-standard-deviation=0.12. Heston kappa=2/year, xi=0.4, rho=−0.7. Matching adjusts only Merton diffusion sigma and Heston v0=theta; all other parameters remain fixed. Fitted Merton sigma is 0.1805621434; Heston v0=theta is 0.0417900377. This fits one European call; put-call parity also matches the paired put. It does not fit an entire smile. Infeasible matches fail visibly; matching below $0.005 time value is rejected as poorly identified. Replay also rejects negative synthetic entry bids under its 5c half-spread. These boundary guards do not change the recorded ATM study.

| Model | Price USD/share | Delta | Gamma /USD | Parameter vega | Vega convention |
| --- | --- | --- | --- | --- | --- |
| Black–Scholes–Merton | 10.45058357 | 0.636831 | 0.01876202 | 37.5240 | diffusion sigma, jump parameters fixed |
| Merton jump-diffusion | 10.45058357 | 0.647225 | 0.01880951 | 33.9628 | diffusion sigma, jump parameters fixed |
| Heston stochastic volatility | 10.45058357 | 0.706822 | 0.01688348 | 15.5249 | initial/current sqrt(variance), theta fixed |

Vega is not interchangeable across columns: BSM/Merton bump diffusion sigma while holding jump parameters fixed; Heston bumps sqrt(current variance) while theta/kappa/xi/rho remain fixed. The parameter calibrated to match the initial premium is not simultaneously recalibrated for the Greek bump. Heston price/current-variance sensitivity is meaningful without equating it to an implied-volatility surface shift.



## Full scenarios and approximation residuals

The signed book is short one matched call and put, multiplier 100, with no shares. Current model volatility/variance parameters are frozen; remaining maturity rolls by 30 calendar days. Spot-only Taylor includes signed delta and half-gamma; it omits theta and time/cross terms. Full minus Taylor remains an explicit residual. These are option mark changes, not financed executed P&L.

| Model | Spot shock | Full mark change USD | Spot Taylor USD | Residual USD |
| --- | --- | --- | --- | --- |
| bsm | -20% | -269.37 | -203.16 | -66.21 |
| bsm | 20% | -1,079.82 | -1,297.80 | 217.98 |
| merton | -20% | -249.16 | -163.48 | -85.68 |
| merton | 20% | -1,108.49 | -1,341.28 | 232.79 |
| heston | -20% | -110.40 | 151.95 | -262.34 |
| heston | 20% | -1,230.52 | -1,502.63 | 272.10 |

At −20% spot, BSM versus Heston full mark changes differ about$158.97 per straddle; the >$10 H8 materiality threshold is supported for this synthetic stress. The ranking depends on the declared fixed-parameter motion and maturity roll, and is not a probability-weighted market prediction.



## Monte Carlo correctness, Greeks and uncertainty

Three independent seeds 811/823/839 and path budgets 8,192/32,768/131,072 use the same requested budgets across models. BSM/Merton sample terminal values exactly in one step; Heston uses 128 QE steps. Price and pathwise delta are accompanied by independent-antithetic-pair normal confidence intervals. Gamma uses common-random-number spot bumps 0.5/0.25/0.125 USD at the anchor, and vega uses ±0.001 parameter-volatility bumps with the same random stream. Every bump result is retained. Individual antithetic legs and time nodes are not treated as independent observations.

All 27 predeclared price checks passed the allowance `abs(error) <= 4*SE + $0.03`. This is a bounded project numerical gate, not a universal accuracy requirement or proof that every 95% interval contains the reference. All price/delta/gamma/vega errors and gamma-bump curves remain in the immutable result; Greek sampling error can be appreciable even when price looks close. Confidence intervals do not cover finite-bump bias or Heston discretisation bias. A thin-payoff sample is not a certificate for tail Greeks.

| Model | Quantity | Mean error across 3 seeds | Per-seed SE range | Reference |
| --- | --- | --- | --- | --- |
| bsm | price | -0.029523 | 0.028481–0.028632 | 10.450584 |
| bsm | delta | -0.000118 | 0.000557–0.000564 | 0.636831 |
| bsm | gamma | 0.000059 | 0.000589–0.000603 | 0.018762 |
| bsm | vega | -0.197429 | 0.180627–0.181645 | 37.524035 |
| merton | price | -0.028575 | 0.027874–0.028133 | 10.450584 |
| merton | delta | -0.000185 | 0.000866–0.000867 | 0.647225 |
| merton | gamma | -0.000075 | 0.000598–0.000605 | 0.018810 |
| merton | vega | -0.183637 | 0.186503–0.187536 | 33.962846 |
| heston | price | -0.002184 | 0.019865–0.019945 | 10.450584 |
| heston | delta | -0.000869 | 0.000895–0.000898 | 0.706822 |
| heston | gamma | -0.000036 | 0.000564–0.000569 | 0.016883 |
| heston | vega | 0.010752 | 0.079308–0.079847 | 15.524910 |



Nested independent antithetic shocks separately couple Heston 32/128/512-step controls with 32,768 paths; coarser Gaussian shocks aggregate the fine increments. The finest-step price is compared with the independent semi-analytical reference. The paired 32/128-minus-512 differences have intervals overlapping zero; this bounds observed weak price differences at this parameter point, without proving continuous-time exactness, universal Greek convergence or hedge-tail convergence across every regime.

| QE steps | Price USD | Sampling SE | Difference to 512 | 95% paired step-difference CI |
| --- | --- | --- | --- | --- |
| 32 | 10.449491 | 0.039025 | -0.003903 | [-0.017661, 0.009855] |
| 128 | 10.451343 | 0.039387 | -0.002051 | [-0.008250, 0.004148] |
| 512 | 10.453394 | 0.039468 | 0.000000 | [0.000000, 0.000000] |

## Causal, paid model hedges

Initial capital is 10,000 USD. The short straddle is entered at a common generator-model premium with 5c/share option half-spread. Every model sees the same present spot and idealised observable variance signal. Initial premium matching and normalization of the observed variance ratio preserve each model's initial fitted volatility. BSM-fixed deliberately ignores later variance changes; BSM-state updates from the same current variance ratio. Merton parameters remain fixed; Heston updates present variance, with theta/kappa/xi/rho fixed. No policy receives future shocks, future variance or a terminal payoff.

Only stock targets differ. BSM/Merton/Heston ordinary policies use their partial spot deltas; Heston-minvariance uses `delta + rho*xi/S * dV/dv`, derived from instantaneous spot/option covariance in the assumed Heston model. At zero variance the instantaneous covariance degenerates and the partial-delta control is used. This is a local instantaneous quadratic-risk hedge, not a globally optimal discrete strategy. It leaves independent variance risk. Ordinary Merton delta does not minimize quadratic jump residuals; this study does not claim to test every feasible jump-risk hedge.

There are 126 equally spaced decision nodes over 365 days: the shared policy identifiers `daily`/`weekly` mean every 1/5 nodes (about 2.90/14.48 calendar days here), not literal daily/weekly execution. BSM-fixed/state, Merton and Heston controls all trade at every scheduled decision node; bsm-weekly is the five-node baseline.

Integer stock targets are bounded at 250 shares and 25,000 USD gross stock-notional plus signed short option-liability magnitude. Decision and later-fill feasibility are checked. Orders execute at the later node quote when delay 1; unresolved orders expire at settlement. Cash funding, left-node stock dividends, execution spreads, European payoff and paid terminal stock liquidation use the shared ledger. Premium received is offset by liability. Financed error is final NAV minus 10,000*exp(r*T), not raw cash income. Reported target-delta residuals use each policy's own model or covariance-adjusted sensitivity; they are not one common cross-model risk measure.

## Protected evaluation and findings

The separately committed protocol was frozen before final seeds 4001/5003/6007. Each model/cost/delay cell has 3,072 independent paths, 126 hedge nodes, four QE substeps per node under Heston, and 154 tail observations. Three generators × three half-spreads 0/1/5c × two delays 0/1 × seven policies produce387,072 episode rows. Paired bootstraps use 2,000 draws and preserve policy pairing by independent path; per-seed batch metrics and ES intervals are retained. Mean/cost/RMSE/ES are conditional on the RN generator, not estimates of trading alpha. Primary H9 requires at least 5% RMSE reduction and paired CI upper below zero against every declared BSM baseline.

Default cell below: one-cent half-spread, one-node execution delay. ES uses exact worst 5% empirical mass with fractional boundary weight. Rejections are counted, not removed from results.

| Generator | Hedger | Mean error USD | RMSE USD | ES95 loss USD | Mean cost USD | Rejected requests |
| --- | --- | --- | --- | --- | --- | --- |
| bsm | none | 12.07 | 1,346.22 | 3,794.91 | 10.00 | 0 |
| bsm | bsm-fixed | -22.45 | 220.19 | 523.58 | 18.13 | 0 |
| bsm | bsm-state | -22.45 | 220.19 | 523.58 | 18.13 | 0 |
| bsm | merton | -23.36 | 225.33 | 557.26 | 18.19 | 0 |
| bsm | heston | -25.98 | 289.90 | 692.96 | 18.18 | 6 |
| bsm | heston-minvariance | -19.68 | 301.10 | 626.69 | 18.25 | 5 |
| bsm | bsm-weekly | -24.01 | 327.57 | 779.36 | 14.16 | 0 |
| merton | none | -22.30 | 1,417.93 | 3,965.08 | 10.00 | 0 |
| merton | bsm-fixed | -6.96 | 443.46 | 1,475.50 | 17.53 | 0 |
| merton | bsm-state | -6.96 | 443.46 | 1,475.50 | 17.53 | 0 |
| merton | merton | -7.34 | 450.10 | 1,509.50 | 17.58 | 0 |
| merton | heston | -9.94 | 499.85 | 1,631.36 | 17.55 | 0 |
| merton | heston-minvariance | -5.77 | 450.79 | 1,336.76 | 17.63 | 103 |
| merton | bsm-weekly | -1.31 | 495.68 | 1,561.61 | 13.95 | 0 |
| heston | none | 19.62 | 1,213.91 | 3,023.28 | 10.00 | 0 |
| heston | bsm-fixed | -22.14 | 464.25 | 1,243.01 | 17.55 | 0 |
| heston | bsm-state | -19.61 | 489.73 | 1,225.30 | 18.28 | 0 |
| heston | merton | -23.04 | 477.08 | 1,284.56 | 17.60 | 0 |
| heston | heston | -23.97 | 540.07 | 1,307.17 | 17.67 | 0 |
| heston | heston-minvariance | -22.70 | 417.37 | 1,042.49 | 17.56 | 0 |
| heston | bsm-weekly | -21.98 | 547.02 | 1,496.49 | 13.95 | 0 |



| Generator | Candidate | Baseline | RMSE difference USD | 95% paired CI | RMSE reduction | Per-baseline gate |
| --- | --- | --- | --- | --- | --- | --- |
| bsm | merton | bsm-fixed | 5.14 | [3.62, 6.70] | -2.33% | False |
| bsm | merton | bsm-state | 5.14 | [3.62, 6.70] | -2.33% | False |
| bsm | merton | bsm-weekly | -102.24 | [-111.41, -92.75] | 31.21% | True |
| bsm | heston | bsm-fixed | 69.72 | [64.35, 75.71] | -31.66% | False |
| bsm | heston | bsm-state | 69.72 | [64.35, 75.71] | -31.66% | False |
| bsm | heston | bsm-weekly | -37.66 | [-47.68, -27.12] | 11.50% | True |
| bsm | heston-minvariance | bsm-fixed | 80.91 | [75.32, 86.41] | -36.75% | False |
| bsm | heston-minvariance | bsm-state | 80.91 | [75.32, 86.41] | -36.75% | False |
| bsm | heston-minvariance | bsm-weekly | -26.47 | [-36.44, -16.73] | 8.08% | True |
| merton | merton | bsm-fixed | 6.64 | [4.88, 8.42] | -1.50% | False |
| merton | merton | bsm-state | 6.64 | [4.88, 8.42] | -1.50% | False |
| merton | merton | bsm-weekly | -45.58 | [-58.45, -33.16] | 9.19% | True |
| merton | heston | bsm-fixed | 56.39 | [47.82, 65.03] | -12.72% | False |
| merton | heston | bsm-state | 56.39 | [47.82, 65.03] | -12.72% | False |
| merton | heston | bsm-weekly | 4.18 | [-10.17, 17.68] | -0.84% | False |
| merton | heston-minvariance | bsm-fixed | 7.33 | [-1.20, 15.61] | -1.65% | False |
| merton | heston-minvariance | bsm-state | 7.33 | [-1.20, 15.61] | -1.65% | False |
| merton | heston-minvariance | bsm-weekly | -44.89 | [-58.30, -31.47] | 9.06% | True |
| heston | merton | bsm-fixed | 12.83 | [11.31, 14.41] | -2.76% | False |
| heston | merton | bsm-state | -12.64 | [-26.36, 1.06] | 2.58% | False |
| heston | merton | bsm-weekly | -69.93 | [-87.21, -52.61] | 12.78% | True |
| heston | heston | bsm-fixed | 75.82 | [63.69, 88.66] | -16.33% | False |
| heston | heston | bsm-state | 50.34 | [43.88, 56.86] | -10.28% | False |
| heston | heston | bsm-weekly | -6.95 | [-27.01, 12.51] | 1.27% | False |
| heston | heston-minvariance | bsm-fixed | -46.88 | [-55.72, -38.47] | 10.10% | True |
| heston | heston-minvariance | bsm-state | -72.36 | [-81.78, -63.09] | 14.78% | True |
| heston | heston-minvariance | bsm-weekly | -129.65 | [-147.65, -112.66] | 23.70% | True |

Under Heston, the minimum-variance hedge RMSE417.37 versus BSM-fixed464.25 is a10.10% conditional reduction (paired difference−46.88USD, CI[−55.72,−38.47]). It also beats BSM-state and weekly under the registered gate. Ordinary Heston delta RMSE540.07 is worse than fixed BSM, showing that a richer price model and a good stock-risk hedge are different choices.

Under Merton, ordinary Merton delta RMSE450.10 versus BSM443.46 fails H9; its paired difference+6.64USD has CI[4.88,8.42]. Jump risk remains in both. Under matched GBM, BSM beats the richer-model hedges. Beating only weekly does not establish superiority over the strongest BSM baseline.

All cost/delay cells are retained. The following candidate/cells pass every BSM-baseline comparison; omitted candidate/cells failed at least one registered comparison:

| Generator | Delay nodes | Half-spread USD/share | Candidate passing all 3 comparisons |
| --- | --- | --- | --- |
| heston | 0 | 0.00 | heston-minvariance |
| heston | 0 | 0.01 | heston-minvariance |
| heston | 0 | 0.05 | heston-minvariance |
| heston | 1 | 0.00 | heston-minvariance |
| heston | 1 | 0.01 | heston-minvariance |
| heston | 1 | 0.05 | heston-minvariance |

These intervals are pointwise, with no multiple-comparison family adjustment. No final-seed tuning, threshold loosening, seed shopping or profitability claim occurred. Initial parameters, policy definitions and path budgets were fixed before testing. Generator discretisation controls address pricing at one anchor; they do not establish continuous-time convergence of every hedge-tail statistic. Current variance observability and known RN parameters are idealised assumptions that would require estimation/calibration and chronology audits for a real-data study.

## Auditable path and costs

Protected Heston path 0, seed 4001, minimum-variance hedger,1c spread, 1 node delay: at node 64/day185.40, spot117.9613, observed variance0.032602. Prior request fills-1share at the current quote; a new6-share request waits. Inventory69, cash4237.32, option liability-2230.65, NAV10146.00. These reconcile as cash + shares*spot + signed option value.

At expiry spot131.3114, outstanding requests expire; cash settlement and paid close of-100shares leave cash/NAV10467.94. Against funding benchmark10,512.71USD this path's financed error is-44.77USD, even though final cash exceeds10,000. This illustrates why raw equity increase is not a replication-profit claim. The UI's exploratory seed 137 trace is separately labelled and is not this protected path.

## Workloads and speed

Mac CPU, float64, locked CPython/NumPy/SciPy/QuantLib runtime. Same requested core output is price/delta/gamma/model-parameter vega at one point. Reference measurements include typed input normalization, all four outputs and JSON serialization, 24 warm repetitions. MC measurements include typed input, simulation, pathwise/bump derivatives, mandatory uncertainty/error diagnostics and serialization, 131,072 paths, 128 Heston steps, three repetitions. Initial premium fitting is excluded from both timed workloads and shown as setup. Imported-process/quad caches are warm; first measured query is not a cold application startup. No browser/network/GPU/transfer time is hidden inside these CPU numbers. MC's extra uncertainty diagnostics are disclosed; timings are not identical numerical work or an argument that MC should beat closed form on a vanilla.

| Model | Reference warm p50 ms | Reference warm p95 ms | MC full query p50 ms |
| --- | --- | --- | --- |
| bsm | 0.0189 | 0.0235 | 3.97 |
| merton | 0.4059 | 0.4253 | 10.54 |
| heston | 0.1704 | 0.1878 | 824.29 |

Analytical/mixture/semi-analytical engines are the practical pricing baselines for these European vanillas. Monte Carlo supplies an independent probabilistic control and a path mechanism for hedging; its uncertainty and cost buy different capabilities. No neural approximation was trained on these new models; the existing bounded American-put surrogate rejection remains unchanged.

## Evidence, reproduction and sources

Study run `d6dd3ad1815f4d8cac62d749951a1609`, code `a819abaa1a541aef5e88fd229782270715bd8a00`, source SHA256 `9f74838197094f20686194b8b2568bf54e4e34f1a9ff99ca7a37291987bb366b`. Protected protocol SHA256 `4bc896b89e250cf419714aabccd8e6dfa11981357360e235b77f9e1243897eb5`. Episodes SHA256 `ad8a0afa60c60e2d7947b7183c5746922c3b3407cf7003f7105132d64f6d79de`. Export run `0c7e666de3b94fefa788ccbf844b46e9` verifies the immutable result and Parquet checksum. Unique results/manifests retained in ignored artifacts/jobs; no datasets, weights or images committed. Reports regenerate from actual completed evidence.

```text
uv sync --locked
uv run orl models
uv run orl model-mc --paths 16384 --steps 128
uv run orl model-replay --generator heston --paths 128
uv run orl model-evaluate --phase development
uv run orl model-evaluate --phase locked
uv run orl model-export
uv run python scripts/write_model_report.py
```

The protected command is an explicit local CPU study (~192.8s on this host for the recorded run), not required in routine tests. Do not overwrite the protocol and rerun its final seeds as if untouched. A tuned follow-up needs a fresh registered protocol and new test seeds. Existing H1–H6 artifacts are untouched. Large/generated evidence stays ignored; reproduce or share the named payloads with their manifests/checksums.

Primary implementation references: [QuantLib Merton mixture](https://github.com/lballabio/QuantLib/blob/master/ql/pricingengines/vanilla/jumpdiffusionengine.cpp), [QuantLib Heston characteristic-function engine](https://github.com/lballabio/QuantLib/blob/master/ql/pricingengines/vanilla/analytichestonengine.cpp), [QuantLib Heston QE and martingale correction](https://github.com/lballabio/QuantLib/blob/master/ql/processes/hestonprocess.cpp), [QuantLib Python European model/engine example](https://github.com/lballabio/QuantLib-SWIG/blob/master/Python/examples/european-option.py). Models independently checked; external reference code does not replace local convergence and cash validation.
