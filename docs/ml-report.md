# Matched-budget surrogate study — ML report

Tom Crook · 4 October 2026 · synthetic numerical research. Run `dea54b8777174042ae249128f43fb7ff`, code `66f89ec7c57e7e9aa46413b9722fa612bc89e541`, CPU float64. Current global acceptance: `{"european/price-only": false, "european/derivative-aware": false, "american/price-only": false, "american/derivative-aware": false}`. Reference fallback is the active workbench engine.

## Design and label eligibility

Price-only versus price-and-delta tanh MLPs, three hidden layers ×48, 5,041 parameters, identical 2,048 training examples, 300 full-batch Adam updates at .003, seeds17/31/47, matched initializations and derivative graphs. Difference is delta loss weight0 versus.25; price loss scale.1, delta scale.5. Both arms compute the graph, even with zero derivative weight, deliberately matching computational work. It is a bounded budget, not evidence of optimal tuning. P/K normalization and S/K inputs are differentiated analytically by autograd: delta d(P/K)/dm, gamma second/K, vega K*d(P/K)/dIV. Known-polynomial fixture independently checks transforms.

Training domain m .7–1.3, tau .1–2 calendar years, IV .1–.5, r .01–.08, q0–.04; ACT365 rounded days. Train seed101, with joint m>1.2/tau<.3 region excluded. Separate 256-point iid701, held709, exercise/near-expiry719, OOD727 sets. Boundary is m .75–1.03/tau1–29days; OOD is tau<.1 and IV>.5. No test region enters training or interpolation labels; seeds/labels/epochs/thresholds fixed before results. Dataset variations are synthetic design sampling, not market distributions.

European control: independent scalar analytical labels, fair vectorized analytical timing; model complexity earns no automatic credit. American target: constant-carry QuantLib FD American put K100, 512 time/spot mesh, damping2, decimal-vega bump .001; selected128/256/512/1024 convergence and CRR4096 independent price checks. Reference gate passed: True. 32 training labels checked at512/1024, max price/delta/gamma/vega differences [.001454, .0000600, .00000565, .008471], allowing delta labels under .005 tolerance. Selected probes do not establish uniform convergence over exercise boundaries.

The boundary set exposed two FD512 negative-gamma shape failures despite zero interpolation error from full fallback. Diagnostic rechecks at1024 changed gamma from −.000137/−.000874 to +.000550/+.000136; price changed by approximately $0.00001. This is reference derivative uncertainty, not surrogate accuracy. Live probes qualify numerical FD Greeks; no clipping hides failures. American numerical prices are not a supported traded early-exercise/assignment simulation.

Grid baseline: 8×5×5×3×3 multilinear price table, 1,710 eligible labels; held cells missing. Missing/OOD cells fall back to reference, with cost included. Grid second differences are unreliable at knots. Price, delta, gamma and decimal-vega errors, bound/shape failures, share-equivalent exposure, scenario and actual integer-share effects are all distinct.

## Accuracy and risk effects

Mean RMSE over the three matched training seeds (K100 per-share price; delta share-equivalent; gamma1/USD; vegaUSD/decimalIV):

| Target | Region | Arm | Price | Delta | Gamma | Vega | Bounds failures /768 | Shape failures /768 |
|---|---|---|---|---|---|---|---|---|
| european | iid | price-only | 0.718080 | 0.080779 | 0.007477 | 7.732604 | 75 | 85 |
| european | iid | derivative-aware | 0.561067 | 0.056850 | 0.005417 | 7.079728 | 64 | 23 |
| european | held-region | price-only | 1.395176 | 0.053995 | 0.007786 | 9.872440 | 416 | 131 |
| european | held-region | derivative-aware | 1.240138 | 0.042398 | 0.006850 | 9.551273 | 395 | 135 |
| european | boundary | price-only | 2.014288 | 0.217872 | 0.035963 | 6.374163 | 241 | 13 |
| european | boundary | derivative-aware | 1.810599 | 0.190649 | 0.035136 | 7.062160 | 259 | 0 |
| european | ood | price-only | 4.879494 | 0.284200 | 0.012908 | 19.841158 | 132 | 50 |
| european | ood | derivative-aware | 4.856908 | 0.254650 | 0.011888 | 20.416712 | 111 | 37 |
| american | iid | price-only | 0.727290 | 0.083149 | 0.010562 | 8.078012 | 93 | 92 |
| american | iid | derivative-aware | 0.581923 | 0.061447 | 0.008800 | 7.314716 | 84 | 38 |
| american | held-region | price-only | 1.347335 | 0.053051 | 0.008197 | 10.188583 | 383 | 187 |
| american | held-region | derivative-aware | 1.191774 | 0.043441 | 0.006926 | 9.359217 | 373 | 178 |
| american | boundary | price-only | 1.984184 | 0.206603 | 0.035893 | 7.475240 | 246 | 8 |
| american | boundary | derivative-aware | 1.815448 | 0.186546 | 0.035681 | 7.867535 | 263 | 5 |
| american | ood | price-only | 5.215102 | 0.294401 | 0.014036 | 19.932913 | 108 | 82 |
| american | ood | derivative-aware | 5.071206 | 0.263648 | 0.012953 | 20.309435 | 83 | 32 |

Paired American iid delta RMSE, aware minus price-only, resampling the same256 synthetic points within each fixed model pair. These intervals condition on the trained models, not training-seed uncertainty:

| Seed | Delta RMSE difference | 95% point-bootstrap CI |
|---|---|---|
| 17 | -0.016396 | [-0.020546, -0.012135] |
| 31 | -0.038362 | [-0.043712, -0.032832] |
| 47 | -0.010348 | [-0.012803, -0.007770] |

H5: derivative-aware American iid delta error improves about26% averaged across these three seeds, with separate boundary/OOD risks. Three seeds are too few for a robust training-variability claim, and gamma/vega improvement is neither guaranteed nor sufficient. No hyperparameter search or learned dynamic hedge is claimed.

| Region | Arm / seed | Scenario error USD/contract | Integer-share mark P&L discrepancy USD |
|---|---|---|---|
| iid | price-only / 17 | 73.72 | 72.82 |
| held-region | price-only / 17 | 98.20 | 63.74 |
| boundary | price-only / 17 | 180.19 | 181.71 |
| ood | price-only / 17 | 247.80 | 255.24 |
| iid | derivative-aware / 17 | 64.15 | 59.92 |
| held-region | derivative-aware / 17 | 85.26 | 58.99 |
| boundary | derivative-aware / 17 | 176.08 | 172.60 |
| ood | derivative-aware / 17 | 240.84 | 239.98 |

Scenario errors are +10% spot/+3 vol points with no time advance; integer shares round100*delta then multiply share discrepancy by ΔS. These are pointwise risk/hedge consequences, not a causal American assignment replay or profit estimate. Reference hedge shares are a numerical control, and no costs are silently attributed to these mark-only comparisons.



Grid RMSE and fallback counts (zero error from full fallback must not be credited to interpolation):

| Target | Region | Price | Delta | Gamma | Vega | Fallback /256 |
|---|---|---|---|---|---|---|
| european | iid | 0.172569 | 0.037091 | 0.067823 | 2.218154 | 11 |
| european | held-region | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 256 |
| european | boundary | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 256 |
| european | ood | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 256 |
| american | iid | 0.255500 | 0.041397 | 0.069940 | 2.726943 | 11 |
| american | held-region | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 256 |
| american | boundary | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 256 |
| american | ood | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 256 |

## Acceptance and speed

Declared in-domain and held-region limits at K100: price .15USD, delta.03, gamma.005, vega2USD/decimalIV RMSE, no bound or shape failure for any training seed. European bounds use discounted strike/spot, American uses intrinsic with a negative-rate-safe upper bound. Boundary/OOD rejects. Every current model fails; H6's joint accuracy-and-speed criterion is not established. No model enters the trading engine.

Fair warm256-point benchmarks include normalization/autograd/output, reference-cache clearing and grid fallback, no CPU transfers. Cold startup/model loading is excluded from warm comparison but separate live total-handler and API cold-first timing are exposed. The analytical European batch is faster than either model. Raw American models are much faster than uncached FD but fail accuracy; active fallback inherits reference cost. Only three repetitions for expensive FD/grid give rough latency quantiles, not deployment SLAs. No CUDA/RTX or MPS result is asserted.

| Target | Method / seed | Region | p50 ms | p95 ms | Batch |
|---|---|---|---|---|---|
| european | grid / reference | iid | 1.294 | 1.478 | 256 |
| european | grid / reference | held-region | 2.116 | 2.211 | 256 |
| european | grid / reference | boundary | 2.106 | 2.192 | 256 |
| european | grid / reference | ood | 2.092 | 2.168 | 256 |
| european | price-only / 17 | iid | 0.492 | 0.509 | 256 |
| european | derivative-aware / 17 | iid | 0.484 | 0.570 | 256 |
| european | vector-reference-price-greeks / reference | iid | 0.034 | 0.039 | 256 |
| european | vector-reference-price / reference | iid | 0.015 | 0.015 | 256 |
| american | grid / reference | iid | 187.544 | 187.681 | 256 |
| american | grid / reference | held-region | 4,341.027 | 4,348.305 | 256 |
| american | grid / reference | boundary | 4,332.221 | 4,335.527 | 256 |
| american | grid / reference | ood | 4,330.566 | 4,337.265 | 256 |
| american | price-only / 17 | iid | 0.484 | 0.492 | 256 |
| american | derivative-aware / 17 | iid | 0.520 | 0.649 | 256 |
| american | fd-reference-price-greeks / reference | iid | 4,351.699 | 4,355.096 | 256 |

Label/build/train costs and storage (parameter bytes exclude buffers, serialization overhead and activations):

| Target | Method / seed | Label/build/train seconds | Parameter/table bytes |
|---|---|---|---|
| european | reference labels / — | 0.014 | — |
| european | grid / — | 0.038 | 14400 |
| european | price-only / 17 | 0.927 | 40328 |
| european | derivative-aware / 17 | 0.901 | 40328 |
| european | price-only / 31 | 0.916 | 40328 |
| european | derivative-aware / 31 | 0.905 | 40328 |
| european | price-only / 47 | 0.901 | 40328 |
| european | derivative-aware / 47 | 0.908 | 40328 |
| american | reference labels / — | 69.452 | — |
| american | grid / — | 81.746 | 14400 |
| american | price-only / 17 | 0.893 | 40328 |
| american | derivative-aware / 17 | 0.896 | 40328 |
| american | price-only / 31 | 0.899 | 40328 |
| american | derivative-aware / 31 | 0.892 | 40328 |
| american | price-only / 47 | 0.897 | 40328 |
| american | derivative-aware / 47 | 0.894 | 40328 |

Reference label generation plus inference costs matter for amortization. Interpolation build time currently includes grid benchmark fallback timing as well as label construction, disclosed here; it is not a pure preprocessing timer. Broad bounds/shapes and frozen domain checks remain necessary even if aggregate RMSE improves. Future improvements require a newly registered protocol and new untouched tests; no post-result loosening of thresholds.

## Trial history, reproducibility and limits

Initial trial7f4b7fc81b8c48ed9602c5d65a90224b failed on acceptance-key mapping after training. Corrected trial7f4c3877b1f24143abb4a8d62e9de422 completed but its European bound counts are superseded because it used American intrinsic bounds. This run changes diagnostic correctness only: same labels, seeds, architecture, losses, optimizer and budgets. No positive result was chosen by repeated tuning. Model payload SHA256 hashes now bind probe weights to the recorded generation; missing/changed payloads fall back. Earlier records remain in the registry.

Run manifest `artifacts/jobs/dea54b8777174042ae249128f43fb7ff.manifest.json`; error payload `artifacts/ml/91bde46a14fd40fc8b7ccdd75dd23c84/surrogate-errors.parquet`, SHA `f5e2d4aa59dcda67595e60353cdaa3c9ee63057d3f853eec8e97b9bf78b0766c`, 12,288 rows. Exact source SHA `54ea0bd1084ac9b85d715be198f30ff46810451dec99ae2dde33406c900be9db`. Pinned versions in `uv.lock`. Reproduce `uv run orl train`, `uv run orl export`, then `uv run python scripts/write_reports.py --output docs`. Raw models/data and generated figures are ignored in Git. This study supplies the required AI contribution through tested acceptance/rejection, not a profitability promise.
