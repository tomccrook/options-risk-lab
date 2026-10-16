"""Render a defensible report from verified immutable evidence, never tune/retrain."""

# Long Markdown prose is intentional.
# ruff: noqa: E501
import json
import math
from pathlib import Path

from options_risk_lab.model_reporting import verified_model_job

job = verified_model_job()
r = job["result"]
export = json.loads(Path("artifacts/model-export.json").read_text())
if export["status"] != "complete":
    raise ValueError("Completed model export required")
e = export["result"]
if e["source_run_id"] != job["id"]:
    raise ValueError("Model export references a different study")


def number(x: float, digits: int = 2) -> str:
    return f"{x:,.{digits}f}"


def table(headers: list[str], rows: list[list[str]]) -> str:
    return (
        "| "
        + " | ".join(headers)
        + " |\n| "
        + " | ".join(["---"] * len(headers))
        + " |\n"
        + "\n".join("| " + " | ".join(row) + " |" for row in rows)
    )


model_rows = [
    [
        x["label"],
        number(x["price"], 8),
        number(x["delta"], 6),
        number(x["gamma"], 8),
        number(x["vega"], 4),
        x["vega_basis"],
    ]
    for x in r["comparison"]["rows"]
]
metric_rows = [
    [
        x["generator"],
        x["hedger"],
        number(x["mean"]),
        number(x["rmse"]),
        number(x["cvar95"]),
        number(x["mean_cost"]),
        str(x["rejected_requests"]),
    ]
    for x in r["summary"]
    if x["spread"] == 0.01 and x["delay"] == 1
]
pair_rows = [
    [
        x["generator"],
        x["hedger"],
        x["baseline"],
        number(x["rmse_difference"]),
        f"[{number(x['ci95'][0])}, {number(x['ci95'][1])}]",
        f"{100 * x['rmse_reduction_fraction']:.2f}%",
        str(x["supports_threshold"]),
    ]
    for x in r["paired"]
    if x["spread"] == 0.01 and x["delay"] == 1
]
mc_rows = []
for model in ("bsm", "merton", "heston"):
    for key in ("price", "delta", "gamma", "vega"):
        rows = [
            x["greeks"][key]
            for x in r["monte_carlo"]
            if x["model"] == model and x["paths"] == 131072
        ]
        mc_rows.append(
            [
                model,
                key,
                number(sum(x["error"] for x in rows) / len(rows), 6),
                f"{min(x['se'] for x in rows):.6f}–{max(x['se'] for x in rows):.6f}",
                number(rows[0]["reference"], 6),
            ]
        )
step_rows = [
    [
        str(x["steps"]),
        number(x["price"]["value"], 6),
        number(x["price"]["se"], 6),
        number(x["paired_difference_to_finest"]["value"], 6),
        f"[{number(x['paired_difference_to_finest']['ci95'][0], 6)}, {number(x['paired_difference_to_finest']['ci95'][1], 6)}]",
    ]
    for x in r["heston_convergence"]
]
stress_rows = [
    [
        x["model"],
        f"{100 * x['spot_return']:.0f}%",
        number(x["full_change"]),
        number(x["spot_taylor"]),
        number(x["residual"]),
    ]
    for x in r["comparison"]["scenarios"]
    if abs(x["spot_return"]) == 0.2
]
timing_rows = [
    [
        x["model"],
        number(x["reference_warm_p50_ms"], 4),
        number(x["reference_warm_p95_ms"], 4),
        number(x["mc_131072_p50_ms"], 2),
    ]
    for x in e["timings"]
]
robust = []
for generator in ("bsm", "merton", "heston"):
    for delay in (0, 1):
        for spread in (0, 0.01, 0.05):
            for hedger in ("merton", "heston", "heston-minvariance"):
                pairs = [
                    p
                    for p in r["paired"]
                    if p["generator"] == generator
                    and p["delay"] == delay
                    and p["spread"] == spread
                    and p["hedger"] == hedger
                ]
                if all(p["supports_threshold"] for p in pairs):
                    robust.append([generator, str(delay), number(spread, 2), hedger])
trace = next(
    x["trace"]
    for x in r["representative_traces"]
    if x["generator"] == "heston" and x["hedger"] == "heston-minvariance"
)
node = trace[64]
terminal = trace[-1]
text = f"""# Model risk and numerical-engine comparison

Owner: Tom Crook, MSc Computational Finance. Synthetic CPU evidence, 2026-10-04. Extension to the completed local laboratory; original H1–H6 protected study and ML outcomes unchanged.

The main finding is conditional: matching the initial option premium does not match risk. Under the declared Heston generator, an instantaneous minimum-variance stock hedge reduced paid financed-error RMSE versus every predeclared BSM baseline. Ordinary Heston delta did worse. Under the Merton generator, Merton delta did not beat the strongest BSM baseline. More complex pricing assumptions do not automatically produce better stock hedges.

## Models and engines

Black–Scholes–Merton assumes constant diffusion volatility. Merton jump-diffusion adds Poisson normal log jumps; it is distinct from the Black–Scholes–Merton name. Heston makes instantaneous variance stochastic, mean reverting and correlated with spot. Monte Carlo is an engine for any of these models, not a fourth asset model.

All inputs are synthetic risk-neutral parameters, with continuous r/q, European cash settlement, USD and ACT/365 calendar time. No market calibration, forecast, historical backtest, real-data entitlement or American assignment lifecycle is asserted. Mac CPU verified; Windows/RTX remains unverified.

BSM's analytical formula is the numerical control. Merton uses a Poisson mixture with stock-numeraire weights and an explicit tail below 1e-14, checked against independent characteristic-function inversion. Installed QuantLib 1.43 Python does not expose JumpDiffusionEngine; this is documented rather than inventing an API. Heston uses stable affine characteristic-function inversion with a BSM control variate, analytic spot derivatives, and initial-variance sensitivity. Composite Gaussian orders 32/64 are compared; difficult points use adaptive quadrature or fail explicitly. Independent QuantLib analytic Heston 192 prices and spot/variance bumps validate the selected grid. At xi=0, a deterministic-variance BSM control and QuantLib European engine supply the limit; no division by zero.

Merton simulation includes the compensated risk-neutral drift `r−q−lambda*(E[J]−1)`, exact lognormal diffusion and Poisson-normal jumps. Heston simulation uses Andersen's quadratic-exponential variance branches plus the conditional MGF martingale correction. Variance remains nonnegative by construction; undefined correction domains reject rather than silently clipping variance or Greeks. QE discretisation bias is measured separately from sampling uncertainty.

## One-point premium matching

The anchor contract is S=K=100, tau=1 year, r=5%, q=0, base BSM sigma=20%. Fixed jump parameters are lambda=0.4/year, log-mean=−0.08, log-standard-deviation=0.12. Heston kappa=2/year, xi=0.4, rho=−0.7. Matching adjusts only Merton diffusion sigma and Heston v0=theta; all other parameters remain fixed. Fitted Merton sigma is {r["parameters"]["merton"]["diffusion_vol"]:.10f}; Heston v0=theta is {r["parameters"]["heston"]["v0"]:.10f}. This fits one European call; put-call parity also matches the paired put. It does not fit an entire smile. Infeasible matches fail visibly; matching below $0.005 time value is rejected as poorly identified. Replay also rejects negative synthetic entry bids under its 5c half-spread. These boundary guards do not change the recorded ATM study.

{table(["Model", "Price USD/share", "Delta", "Gamma /USD", "Parameter vega", "Vega convention"], model_rows)}

Vega is not interchangeable across columns: BSM/Merton bump diffusion sigma while holding jump parameters fixed; Heston bumps sqrt(current variance) while theta/kappa/xi/rho remain fixed. The parameter calibrated to match the initial premium is not simultaneously recalibrated for the Greek bump. Heston price/current-variance sensitivity is meaningful without equating it to an implied-volatility surface shift.

![Matched model curves](../artifacts/model-report/model-curves.png)

## Full scenarios and approximation residuals

The signed book is short one matched call and put, multiplier 100, with no shares. Current model volatility/variance parameters are frozen; remaining maturity rolls by 30 calendar days. Spot-only Taylor includes signed delta and half-gamma; it omits theta and time/cross terms. Full minus Taylor remains an explicit residual. These are option mark changes, not financed executed P&L.

{table(["Model", "Spot shock", "Full mark change USD", "Spot Taylor USD", "Residual USD"], stress_rows)}

At −20% spot, BSM versus Heston full mark changes differ about${abs(stress_rows and next(x["full_change"] for x in r["comparison"]["scenarios"] if x["model"] == "bsm" and x["spot_return"] == -0.2) - next(x["full_change"] for x in r["comparison"]["scenarios"] if x["model"] == "heston" and x["spot_return"] == -0.2)):.2f} per straddle; the >$10 H8 materiality threshold is supported for this synthetic stress. The ranking depends on the declared fixed-parameter motion and maturity roll, and is not a probability-weighted market prediction.

![Model stress repricing](../artifacts/model-report/model-stress.png)

## Monte Carlo correctness, Greeks and uncertainty

Three independent seeds 811/823/839 and path budgets 8,192/32,768/131,072 use the same requested budgets across models. BSM/Merton sample terminal values exactly in one step; Heston uses 128 QE steps. Price and pathwise delta are accompanied by independent-antithetic-pair normal confidence intervals. Gamma uses common-random-number spot bumps 0.5/0.25/0.125 USD at the anchor, and vega uses ±0.001 parameter-volatility bumps with the same random stream. Every bump result is retained. Individual antithetic legs and time nodes are not treated as independent observations.

All 27 predeclared price checks passed the allowance `abs(error) <= 4*SE + $0.03`. This is a bounded project numerical gate, not a universal accuracy requirement or proof that every 95% interval contains the reference. All price/delta/gamma/vega errors and gamma-bump curves remain in the immutable result; Greek sampling error can be appreciable even when price looks close. Confidence intervals do not cover finite-bump bias or Heston discretisation bias. A thin-payoff sample is not a certificate for tail Greeks.

{table(["Model", "Quantity", "Mean error across 3 seeds", "Per-seed SE range", "Reference"], mc_rows)}

![MC price convergence](../artifacts/model-report/mc-convergence.png)

Nested independent antithetic shocks separately couple Heston 32/128/512-step controls with 32,768 paths; coarser Gaussian shocks aggregate the fine increments. The finest-step price is compared with the independent semi-analytical reference. The paired 32/128-minus-512 differences have intervals overlapping zero; this bounds observed weak price differences at this parameter point, without proving continuous-time exactness, universal Greek convergence or hedge-tail convergence across every regime.

{table(["QE steps", "Price USD", "Sampling SE", "Difference to 512", "95% paired step-difference CI"], step_rows)}

## Causal, paid model hedges

Initial capital is 10,000 USD. The short straddle is entered at a common generator-model premium with 5c/share option half-spread. Every model sees the same present spot and idealised observable variance signal. Initial premium matching and normalization of the observed variance ratio preserve each model's initial fitted volatility. BSM-fixed deliberately ignores later variance changes; BSM-state updates from the same current variance ratio. Merton parameters remain fixed; Heston updates present variance, with theta/kappa/xi/rho fixed. No policy receives future shocks, future variance or a terminal payoff.

Only stock targets differ. BSM/Merton/Heston ordinary policies use their partial spot deltas; Heston-minvariance uses `delta + rho*xi/S * dV/dv`, derived from instantaneous spot/option covariance in the assumed Heston model. At zero variance the instantaneous covariance degenerates and the partial-delta control is used. This is a local instantaneous quadratic-risk hedge, not a globally optimal discrete strategy. It leaves independent variance risk. Ordinary Merton delta does not minimize quadratic jump residuals; this study does not claim to test every feasible jump-risk hedge.

There are 126 equally spaced decision nodes over 365 days: the shared policy identifiers `daily`/`weekly` mean every 1/5 nodes (about 2.90/14.48 calendar days here), not literal daily/weekly execution. BSM-fixed/state, Merton and Heston controls all trade at every scheduled decision node; bsm-weekly is the five-node baseline.

Integer stock targets are bounded at 250 shares and 25,000 USD gross stock-notional plus signed short option-liability magnitude. Decision and later-fill feasibility are checked. Orders execute at the later node quote when delay 1; unresolved orders expire at settlement. Cash funding, left-node stock dividends, execution spreads, European payoff and paid terminal stock liquidation use the shared ledger. Premium received is offset by liability. Financed error is final NAV minus 10,000*exp(r*T), not raw cash income. Reported target-delta residuals use each policy's own model or covariance-adjusted sensitivity; they are not one common cross-model risk measure.

## Protected evaluation and findings

The separately committed protocol was frozen before final seeds 4001/5003/6007. Each model/cost/delay cell has 3,072 independent paths, 126 hedge nodes, four QE substeps per node under Heston, and 154 tail observations. Three generators × three half-spreads 0/1/5c × two delays 0/1 × seven policies produce{r["episodes"]["rows"]:,} episode rows. Paired bootstraps use 2,000 draws and preserve policy pairing by independent path; per-seed batch metrics and ES intervals are retained. Mean/cost/RMSE/ES are conditional on the RN generator, not estimates of trading alpha. Primary H9 requires at least 5% RMSE reduction and paired CI upper below zero against every declared BSM baseline.

Default cell below: one-cent half-spread, one-node execution delay. ES uses exact worst 5% empirical mass with fractional boundary weight. Rejections are counted, not removed from results.

{table(["Generator", "Hedger", "Mean error USD", "RMSE USD", "ES95 loss USD", "Mean cost USD", "Rejected requests"], metric_rows)}

![Paid model hedge comparison](../artifacts/model-report/paid-model-hedges.png)

{table(["Generator", "Candidate", "Baseline", "RMSE difference USD", "95% paired CI", "RMSE reduction", "Per-baseline gate"], pair_rows)}

Under Heston, the minimum-variance hedge RMSE417.37 versus BSM-fixed464.25 is a10.10% conditional reduction (paired difference−46.88USD, CI[−55.72,−38.47]). It also beats BSM-state and weekly under the registered gate. Ordinary Heston delta RMSE540.07 is worse than fixed BSM, showing that a richer price model and a good stock-risk hedge are different choices.

Under Merton, ordinary Merton delta RMSE450.10 versus BSM443.46 fails H9; its paired difference+6.64USD has CI[4.88,8.42]. Jump risk remains in both. Under matched GBM, BSM beats the richer-model hedges. Beating only weekly does not establish superiority over the strongest BSM baseline.

All cost/delay cells are retained. The following candidate/cells pass every BSM-baseline comparison; omitted candidate/cells failed at least one registered comparison:

{table(["Generator", "Delay nodes", "Half-spread USD/share", "Candidate passing all 3 comparisons"], robust)}

These intervals are pointwise, with no multiple-comparison family adjustment. No final-seed tuning, threshold loosening, seed shopping or profitability claim occurred. Initial parameters, policy definitions and path budgets were fixed before testing. Generator discretisation controls address pricing at one anchor; they do not establish continuous-time convergence of every hedge-tail statistic. Current variance observability and known RN parameters are idealised assumptions that would require estimation/calibration and chronology audits for a real-data study.

## Auditable path and costs

Protected Heston path 0, seed 4001, minimum-variance hedger,1c spread, 1 node delay: at node 64/day{node["days"]:.2f}, spot{node["spot"]:.4f}, observed variance{node["variance"]:.6f}. Prior request fills{node["fill"]:.0f}share at the current quote; a new{node["request"]:.0f}-share request waits. Inventory{node["shares"]:.0f}, cash{node["cash"]:.2f}, option liability{node["option_value"]:.2f}, NAV{node["nav"]:.2f}. These reconcile as cash + shares*spot + signed option value.

At expiry spot{terminal["spot"]:.4f}, outstanding requests expire; cash settlement and paid close of{terminal["fill"]:.0f}shares leave cash/NAV{terminal["cash"]:.2f}. Against funding benchmark10,512.71USD this path's financed error is{terminal["cash"] - 10000 * math.exp(0.05):.2f}USD, even though final cash exceeds10,000. This illustrates why raw equity increase is not a replication-profit claim. The UI's exploratory seed 137 trace is separately labelled and is not this protected path.

## Workloads and speed

Mac CPU, float64, locked CPython/NumPy/SciPy/QuantLib runtime. Same requested core output is price/delta/gamma/model-parameter vega at one point. Reference measurements include typed input normalization, all four outputs and JSON serialization, 24 warm repetitions. MC measurements include typed input, simulation, pathwise/bump derivatives, mandatory uncertainty/error diagnostics and serialization, 131,072 paths, 128 Heston steps, three repetitions. Initial premium fitting is excluded from both timed workloads and shown as setup. Imported-process/quad caches are warm; first measured query is not a cold application startup. No browser/network/GPU/transfer time is hidden inside these CPU numbers. MC's extra uncertainty diagnostics are disclosed; timings are not identical numerical work or an argument that MC should beat closed form on a vanilla.

{table(["Model", "Reference warm p50 ms", "Reference warm p95 ms", "MC full query p50 ms"], timing_rows)}

Analytical/mixture/semi-analytical engines are the practical pricing baselines for these European vanillas. Monte Carlo supplies an independent probabilistic control and a path mechanism for hedging; its uncertainty and cost buy different capabilities. No neural approximation was trained on these new models; the existing bounded American-put surrogate rejection remains unchanged.

## Evidence, reproduction and sources

Study run `{job["id"]}`, code `{job["manifest"]["provenance"]["code_revision"]}`, source SHA256 `{job["manifest"]["provenance"]["source_sha256"]}`. Protected protocol SHA256 `{r["protocol_sha256"]}`. Episodes SHA256 `{r["episodes"]["sha256"]}`. Export run `{export["id"]}` verifies the immutable result and Parquet checksum. Unique results/manifests retained in ignored artifacts/jobs; no datasets, weights or images committed. Reports regenerate from actual completed evidence.

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

The protected command is an explicit local CPU study (~{r["elapsed_seconds"]:.1f}s on this host for the recorded run), not required in routine tests. Do not overwrite the protocol and rerun its final seeds as if untouched. A tuned follow-up needs a fresh registered protocol and new test seeds. Existing H1–H6 artifacts are untouched. Large/generated evidence stays ignored; reproduce or share the named payloads with their manifests/checksums.

Primary implementation references: [QuantLib Merton mixture](https://github.com/lballabio/QuantLib/blob/master/ql/pricingengines/vanilla/jumpdiffusionengine.cpp), [QuantLib Heston characteristic-function engine](https://github.com/lballabio/QuantLib/blob/master/ql/pricingengines/vanilla/analytichestonengine.cpp), [QuantLib Heston QE and martingale correction](https://github.com/lballabio/QuantLib/blob/master/ql/processes/hestonprocess.cpp), [QuantLib Python European model/engine example](https://github.com/lballabio/QuantLib-SWIG/blob/master/Python/examples/european-option.py). Models independently checked; external reference code does not replace local convergence and cash validation.
"""
Path("docs/model-risk-report.md").write_text(text)
print("Wrote docs/model-risk-report.md from", job["id"])
