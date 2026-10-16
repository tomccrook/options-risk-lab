# Hypothesis and experiment registry

Registry v1, created before experiments. Primary thresholds are project decisions. No predetermined positive result required. Immutable config hash and Git revision accompany every run, including failures. Exploratory trials are separately labelled.

| Study | Primary metric / threshold | Strong baseline | Eligibility / budget |
|---|---|---|---|
| H1 local approximation | Absolute full-minus-Taylor residual; material > $10 per default book | Full BSM repricing | Small and ±20% spot / ±5 vol point / 30-day stresses; boundary failures excluded visibly |
| H2 delta band | Paired financed-error RMSE; ≥5% reduction to support claim | Best predeclared fixed schedule, not only no hedge | Same paths/information, costs 0/1/5 cents per share; band 10 shares fixed before test |
| H3 scenario hedge | Conditional 95% CVaR; ≥5% reduction at comparable feasible budget | Rounded local D/G and D/G/V; no hedge; shares only | Same candidate limits, explicit cost/capital; all integer outcomes reprice |
| H4 surface motion | Worst stress loss difference; material > $10 | Frozen assigned strike IV | Identical states; sticky-log-moneyness; invalid surface rejects |
| H5 differential ML | Delta RMSE; ≥10% paired seed reduction | Same price-only tanh MLP | Same 2048 labels, architecture, 300 epochs, optimizer, float64 CPU; 3 seeds; price/gamma/vega separately reported |
| H6 speed/accuracy | End-to-end inference speed ≥2× AND all declared error limits | Vectorized European, FD American, interpolation | Include preprocessing, derivatives, fallback; otherwise reject surrogate |

Locked path/config regions are in `configs/evaluation.json`. Development/validation seeds must not enter final testing. Exact empirical CVaR integrates the worst 5% mass with fractional boundary observation; paired intervals resample pooled independent paths across seed batches, preserving pairing; separate per-batch metrics are retained. Time nodes are never sampling units. Final tail count ≥150 overall is a minimum, not a precision guarantee. Pilot variance and observed interval widths determine limitations; no repeated seed shopping.

Training target domain: m 0.7–1.3, tau 0.1–2, sigma 0.1–0.5, r 0.01–0.08, q 0–0.04. Held-out region m 1.2–1.3 with tau 0.1–0.3; unseen regime tau <0.1 and sigma >0.5; near-exercise/expiry probes and outside-domain gates. Acceptance separately requires price $0.15, delta .03, gamma .005/share, decimal vega $2 RMSE at K=100. These are illustrative risk-study requirements, not industry standards.

## Completed runs and outcomes

| Run / type | Status / evidence |
|---|---|
| 9af562d826af42c2a5ed9f42aa7b03d5 / development pilot | Complete; exploratory128paths/seed11,29; not final evidence |
| d8098ca0fbc9474c800f01ca43f90328 / locked hedge evaluation | Complete; protected protocolSHA312cd60e…;138,240episode rows; all45cells/27paired comparisons retained |
| 7f4b7fc81b8c48ed9602c5d65a90224b / first ML trial | Failed acceptance-key mapping; persisted failure; no valid acceptance result |
| 7f4c3877b1f24143abb4a8d62e9de422 / corrected ML trial | Completed; superseded European bound diagnostics (American intrinsic incorrectly applied); budgets and seeds unchanged |
| dea54b8777174042ae249128f43fb7ff / corrected style-specific ML study | Complete at66f89ec; same protocol/labels/seeds/budgets;12,288error rows and hashed weights; all four global arm/target gates rejected |
| 0be89d3bf5c848b7b6e87f57c33f7cea / export attempt | Failed request-field name; preserved; no scientific finding |
| e73c1c10c0754cbd86e11b6a004079c0 / first scientific export | Completed using earlier ML trial; superseded for European bound diagnostics |
| 21c113324ff1416db858cf8a69b2d2a2 / scientific export | Complete; corrected study, default case, stress supports/budgets, motion/approximation controls, figures and Parquet |
| 479c918af4114451ae2f62e0ad0a8e9e / final figure export | Complete; same studies/numerics, clearer independent ML layout and discrete cost-budget step frontier |

H1 supported for the adverse delta-hedged book (absolute residual$241.81 >$10). Ideal D/G/V matching still leaves a finite loss$34.69, although that particular positive-stress residual is only$2.48. H2 not supported against daily in matched model: band-minus-daily RMSE+$42.11,95%CI[38.80,45.28] at one-cent half-spread. Misspecified/jump band-versus-daily intervals overlap zero. H3 supported conditionally on default15states: scenario CVaR72.30 versus strong rounded D/G/V101.49 with similar costs; not out-of-sample market evidence. Support and budget sensitivity retained. H4 supported as a synthetic assumption effect: frozen/sticky worst mark losses differ$134.74 on the same initial book. H5 American iid delta improvement about26% over three matched seeds; conditional point-bootstrap intervals/per-seed errors in ML report, limited training-seed precision. H6 rejected: joint accuracy/speed requirements fail; all surrogate arms remain inactive.

Default static diagnostic supports: wide±20/10/0% and narrow±10/5/0% spot crossed with±5/0volpoints,30days; budgets0/25/100 before enumeration. These are explanatory post-lock sensitivity experiments, not changes to replay/model policy. No more strategy tuning occurred after final tests. Validation seeds43/61 were reserved but not used to tune anything; protected tests were run against the predeclared untuned band. A future tuned study must add validation work and a fresh untouched test protocol.

Immutable manifest/result files and SQLite statuses in ignored `artifacts/jobs/` store code/config/source/version hashes, device/platform, timing and failures. JSON convenience aliases can be replaced; evaluation/model raw payload directories are unique in subsequent runs. Sharing requires preserving the named original job/payloads. Reconstruct with documented commands and the exact lock; numerical values may match while measured wall times differ by host/load. See [research report](research-report.md) and [ML report](ml-report.md) for linked evidence and qualifications.

## Registered model-risk extension H7–H9 (before final evaluation)

H7: numerical engines recover the same European model price and Greeks. Primary price check: analytic/reference differences within four reported standard errors plus the declared numerical allowance; Greek error and CRN bump sensitivity separately. Merton mixture tail <1e-14; Heston independent characteristic-function versus QuantLib and order refinement, price tolerance $1e-5, delta 5e-5, gamma 1e-5, vega0 $1e-3 on eligible points. Heston MC step bias is separate from confidence intervals.

H8: synthetic jump/stochastic-volatility assumptions alter delta, gamma and stress repricing after one-point initial premium matching. Primary materiality: >$10 stress difference per signed 100-multiplier short straddle; no ranking interpreted as a market forecast.

H9: changing the hedge model reduces financed-error RMSE by ≥5% relative to the strongest predeclared BSM baseline on the same independent paths, costs, information, constraints and premium. Baselines: unhedged; fixed-IV BSM daily; current-variance BSM daily; Merton daily; Heston partial delta daily; Heston local minimum-variance stock hedge daily; weekly fixed-IV BSM. Stocks integer, max250, gross capital25000; allocated10000; option spread5c/share; stock half-spreads 0/1/5c; execution delays 0/1 node. Primary comparisons and independent-path paired CIs retained even when superiority fails. Separate registry/protected protocol will be committed before final seeds are run; existing H1–H6 tests and results remain unchanged.

Development seeds137/251; final seeds 4001/5003/6007; pricing seeds 811/823/839; no tuning on final results. Path budget1024 per final seed yields154 tail observations per cell; interval precision and discretisation limitations disclosed. Fixed RN generators BSM/Merton/Heston and 126 hedge nodes, Heston substeps4; convergence controls use nested increments separately. No dynamic option lifecycle or American assignment extension.

Development pilot `890aa66fd3ff479f9e293b41c0854a00` completed before protected evaluation, with256paths/cell and32,256episodes. Source includes uncommitted prototype recorded in source hash; not final evidence. No thresholds or model/policy parameters were tuned from outcomes. Current-variance controls normalize the observed variance ratio to each model’s initial fitted volatility; the ratio is shared current information. Minimum-variance delta uses Heston’s assumed instantaneous covariance; incomplete-market residual and discrete/cost effects remain.

The extension’s shared policy identifiers daily/weekly refer to every1/5decision nodes, not literal calendar schedules:126equalACT/365nodes/year imply2.90/14.48calendar days. No schedule parameters changed after the protected run; this clarifies the actual convention.


Completed protected model study `d6dd3ad1815f4d8cac62d749951a1609` at committed `a819aba`:387,072episodes,126summarycells,162paired comparisons,27MC checks. Numerical price gates all pass; Heston32/128minus512step paired price intervals overlap zero, with finite-step/Greek/hedge-tail limitations retained.2,645adaptive integration refinements, no hidden clipping. H8 materiality supported at−20%/30days: BSM/Heston short-straddle mark changes differ$158.97. H9 supports Heston minimum-variance conditionally under Heston:1c/delay 1RMSE417.37 versus BSM464.25 (−46.88,CI[−55.72,−38.47]); beats all3BSM baselines. Ordinary Heston delta and Merton delta do not support broad superiority. No final-seed tuning; pointwise comparisons, no multiple-testing family correction. [Full report](model-risk-report.md) retains every cost/delay cell and failure.

Scientific exports `c85f7bdddcb24ac6bcc384c550c8de6e` and `86d6a66443544d5994121d4fbd222c49` use the same protected evidence; the second adds consistent typed-input/output-serialization CPU timing and labels first-query/warm conditions accurately. Subsequent figure-caption export changes presentation only, not policies/results. Thin-time-value matching/negative-bid boundary guards were added after the study without changing the valid frozen ATM inputs, results, thresholds or policy schedules.

Final captioned scientific export `0c7e666de3b94fefa788ccbf844b46e9` verified the same protected source run and episodes, added standalone workload/assumption titles, and refreshed CPU timings; no research retuning.
