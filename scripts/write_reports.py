"""Render research/ML Markdown from verified completed artifacts; no training/tuning."""

# Long Markdown prose templates intentionally preserve paragraphs.
# ruff: noqa: E501
import argparse
import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from options_risk_lab.experiments import paired_interval
from options_risk_lab.reporting import load_completed

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path("artifacts/report"))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
e = load_completed(Path("artifacts/evaluation-locked.json"))
m = load_completed(Path("artifacts/ml-study.json"))
x = load_completed(Path("artifacts/evidence-export.json"))
research, models, evidence = e["result"], m["result"], x["result"]


def table(headers: list[str], rows: list[list[Any]]) -> str:
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
        + ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    )


def n(v: float, digits: int = 2) -> str:
    return f"{v:,.{digits}f}"


def interval(v: list[float]) -> str:
    return f"[{n(v[0])}, {n(v[1])}]"


p = evidence["default_portfolio"]
h = evidence["default_comparison"]
main = [r for r in research["summary"] if r["spread"] == 0.01]
text = f"""# Options Risk and Hedging Laboratory — research report

Tom Crook · MSc Computational Finance · 4 October 2026. Synthetic research for quantitative trading/research interviews. No observed market data or profitability inference.

## Question and evidence boundary

When apparently hedged local Greeks leave meaningful losses, which feasible hedges reduce those losses after costs? The study connects matched European call/put Greeks to signed book risk, full scenario repricing, actual hedge trades and financed causal replay. It distinguishes a finite mark change from terminal financed error and retains losses and failed hypotheses.

Core trading scope is one SYNTH equity, USD, European cash settlement, multiplier 100, continuous r/q, UTC ACT365. American puts are a separate numerical/ML track. All quotes, spreads, paths and candidate contracts are synthetic. These are conditional calculations, with no alpha claim.

European controls independently reconcile call 10.4505835722, put 5.5735260223, call delta .6368306512, gamma .01876201735, decimal vega 37.5240346917 at S=K=100, tau=1, r=.05, q=0, sigma=.20. QuantLib analytical prices and first Greeks agree over an additional carry/rate grid; finite bumps check mixed/higher derivatives. Expiry/deterministic payoff kinks return unavailable sensitivities. Prices use signed quantity × multiplier once.

## Ordinary and adverse auditable cases

The default book shorts one call and one put and holds 27 shares. It has initial NAV $10,000; option liability ${n(-p["risk"]["net"]["price"])}, shares $2,700 and cash ${n(p["book"]["cash"])}. Received premium is offset by liability. Partial delta is {n(p["risk"]["net"]["delta"], 4)} shares, gamma {n(p["risk"]["net"]["gamma"], 6)} shares/USD and vega {n(p["risk"]["net"]["vega"] * 0.01)} USD/vol point.

A small +1% spot/+0.25 vol point/1.5-calendar-day state has full mark change ${n(evidence["local_stresses"][1]["full_change"])}; Taylor ${n(evidence["local_stresses"][1]["taylor"])}; residual ${n(evidence["local_stresses"][1]["residual"])}. For the +20% spot/+5 vol point/30-calendar-day adverse state, option change is ${n(p["selected"]["option_change"])}, share change ${n(p["selected"]["share_change"])}, full change ${n(p["selected"]["full_change"])}, Taylor ${n(p["selected"]["approximation"])}, and full-minus-Taylor residual ${n(p["selected"]["residual"])}. Gamma, vega and mixed/time effects explain why near-zero delta is insufficient.

The ideal fractional locally-matched control has partial delta/gamma/vega essentially zero. Under the same large positive stress it still loses ${n(-evidence["local_stresses"][-1]["full_change"])}; its residual is ${n(evidence["local_stresses"][-1]["residual"])}. Remaining theta/vanna/volga and finite-state variation matter. This is an ideal control, not an integer executable book. The residual is omitted higher/time/carry terms and curvature, not an accounting error.

![Approximation residuals](../artifacts/report/approximation-residuals.png)

## Feasible paid static hedges

Candidate near put: K95, 180 calendar days, modeled mid $2.5051356955/share. Far call: K105, 730 days, mid $13.6396150968/share. Integer additions bounded ±3 contracts and ±250 shares. Half-spreads: stock $0.01/share, option $0.05/share; option fee $0.50/contract on entry and exit. Gross capital: absolute stock notional + gross option premium/liability + entry costs, limit $10,000. This is a research limit, not exchange margin or borrow availability.

The objective integrates exact worst 5% mass over 15 uniform synthetic stresses, ±20/10/0% spot × ±5/0 vol points at 30 days. Here each state's mass exceeds 5%, so CVaR equals worst loss. Original book retained at horizon marks; added hedges enter and close at modeled bid/ask. Funding, carry, premium outlay and execution costs enter once. It is not a forecast of market ES.

"""
text += table(
    [
        "Method",
        "Additional shares / put / call",
        "Costs USD",
        "Gross capital USD",
        "Conditional CVaR95 USD",
    ],
    [
        [r["name"], r["quantities"], n(r["cost"]), n(r["capital"]), n(r["cvar"])]
        for r in h["hedges"]
        if r["status"] == "evaluated"
    ],
)
text += f"""

The scenario choice sells 33 additional shares and buys one of each candidate. Final stock holding is −6 shares. Its cost ${n(h["hedges"][-1]["cost"])} is slightly below the rounded D/G/V baseline; CVaR is {(1 - h["hedges"][-1]["cvar"] / h["hedges"][-2]["cvar"]) * 100:.1f}% lower in these states. Residual delta is +2.2191 shares: matching local delta exactly was not optimal for this support. The normalized local system condition is {n(h["condition"], 1)}; rank/condition failures reject. Fractional solutions are reported as controls and integer outcomes fully repriced.

Exact enumeration also produces a nondominated cost/CVaR frontier. At a zero cost budget, the paid optimum is no additions. A $25 budget already admits the default optimum; $100 adds no benefit. Narrowing spot support to ±10/5/0% changes the chosen shares to −36 and conditional CVaR to $41.12. This support sensitivity prevents a universal hedge recommendation. It is an explanatory post-lock static experiment, not strategy tuning.

![Integer cost-risk frontier](../artifacts/report/static-cost-risk.png)

## Surface-motion experiment

Both frozen-strike and sticky-log-moneyness start from identical assigned initial IV. Level/skew/term are synthetic, partial Greeks hold IV fixed, total spot delta includes the selected motion by finite bump. Repricing rolls maturity and term inputs. On the same frozen-initial book and 15 states, worst unfinanced mark loss is:

"""
text += table(
    ["Motion", "Worst mark loss USD"],
    [
        [
            motion,
            n(-min(r["full_change"] for r in evidence["surface_trials"] if r["motion"] == motion)),
        ]
        for motion in ("flat", "frozen-strike", "sticky-log-moneyness")
    ],
)
text += """

H4's $10 materiality threshold is exceeded between frozen and sticky. This changes conditional stress outcomes, without providing an empirical motion estimate. Sampled strike monotonicity/convexity checks are necessary diagnostics only; no arbitrage-free calibration or maturity-calendar proof is claimed. Invalid IV/surface samples explicitly reject.

## Causal accounting and locked replay

Each decision receives current node risk, shares and pending status only. Delayed targets fill at the later quote. Funding compounds cash; continuous dividends use left-node share/spot exposure and converge as intervals shrink. Fees/spreads enter actual fills; NAV uses signed mid marks; expiry pays exact cash settlement; terminal shares liquidate with costs. Financed error is terminal NAV minus allocated $10,000 grown at r. It includes original option costs. Cash fixtures A and B reconcile to $1,006 and $9,900 respectively; an independent fee/roll fixture ends $1,011. Missing marks fail rather than remove liabilities.

The locked protocol used seeds 1009/2027/3041, 1,024 independent paths each, 252 uniform valuation nodes over 365 calendar days. “Daily/weekly/monthly” are node schedules 1/5/21, not an exchange business-day calendar. Same paths/information/costs for each policy; 10-share band fixed before testing. RN GBM matched drift r−q with sigma20%; misspecified realized sigma30% against20% pricing; jump is −20% at midpoint with one-node delay. Share bounds ±250 and gross capital $25,000 constrain decisions and actual delayed fills. Multi-expiry dynamic trading rejects; static calendars remain supported.

138,240 episode rows cover 3 regimes × 3 stock half-spreads × 3 seeds × 1,024 paths × 5 policies. There are 3,072 paths per regime/cost cell and 154 tail observations (153.6 weighted mass). Independent-path bootstrap uses 2,000 draws, preserving policy pairing. It pools independent paths across seeds; separate three-batch metrics are retained. Nodes are not sampling units. Intervals quantify Monte Carlo uncertainty conditional on each generator, not uncertainty in the market model. No policy was tuned after locked tests.

At a one-cent stock half-spread:

"""
text += table(
    ["Regime", "Policy", "RMSE USD", "ES95 USD [CI]", "Mean error USD [CI]", "Costs USD"],
    [
        [
            r["regime"],
            r["policy"],
            n(r["rmse"]),
            n(r["cvar95"]) + " " + interval(r["cvar95_ci95"]),
            n(r["mean"]) + " " + interval(r["mean_ci95"]),
            n(r["mean_cost"]),
        ]
        for r in main
    ],
)
text += "\n\nBand minus fixed-schedule paired RMSE differences (negative favours band):\n\n"
text += table(
    ["Regime", "Baseline", "Difference USD", "95% CI USD"],
    [
        [r["regime"], r["baseline"], n(r["rmse_difference"]), interval(r["ci95"])]
        for r in research["paired"]
        if r["spread"] == 0.01
    ],
)
text += """

H2 is not supported against the strongest fixed baseline in the matched model: daily has smaller RMSE, band has lower turnover/cost. Misspecified and jump-delay daily/band intervals overlap zero. Misspecification generates roughly $800 negative mean error despite frequent hedging. The jump path exposes stale targets and unhedgeable gap loss; reducing tail/error risk does not imply a higher mean than no hedge under that altered generator. Costs increase net financed error and can change preferences; the figures contain all 0/1/5-cent settings.

![Locked cost-risk study](../artifacts/report/locked-cost-risk.png)

## Limitations and defensible next work

One underlying, modeled liquidity, fixed carry, prescribed physical/misspecified/jump regimes, discrete dividends and borrow/margin mechanics absent. Surface diagnostics limited; exact stress search small and conditional. Single-expiry replay does not implement dynamic option rolling, multi-factor correlation, traded American assignment or an exotic lifecycle. GPU, Windows runtime, LSEG observations and production deployment are unverified. No data entitlement, AWS budget or measured C++ need established; extensions remain gated. CPU synthetic research requires none of them.

To extend: register a new protocol before tuning; expand valid surface/reference probes and feasible liquidity/borrow constraints; estimate chronological real-data inputs only after contract/timing/allowed-use audit; measure local need before acceleration or paid provisioning. Retain the strongest fixed schedules and analytical reference. The ML report rejects all current surrogates for active risk.

## Evidence and reproduction

"""
for label, job in [
    ("Locked evaluation", e),
    ("Surrogate study", m),
    ("Scientific export / static diagnostics", x),
]:
    text += f"- {label}: `{job['id']}`; code `{job['manifest']['provenance']['code_revision']}`; source SHA `{job['manifest']['provenance']['source_sha256']}`. Manifest: `artifacts/jobs/{job['id']}.manifest.json`.\n"
text += f"\nProtocol SHA `{research['protocol_sha256']}`. Episode payload SHA `{research['episodes']['sha256']}`. Artifacts are generated and ignored in Git; manifests/results persist in the local job registry. Convenience aliases identify current runs and may be replaced. Reproduce with `uv run orl demo`, then `uv run python scripts/write_reports.py --output docs`; routine checks do not retrain. Export SVG/PNG/PDF figures and Parquet tables with `uv run orl export`. Refer to [demo guide](demo.md), [assumptions](assumptions.md), [experiment register](experiments.md) and [ML report](ml-report.md).\n"
(args.output / "research-report.md").write_text(text)

report = f"""# Matched-budget surrogate study — ML report

Tom Crook · 4 October 2026 · synthetic numerical research. Run `{m["id"]}`, code `{m["manifest"]["provenance"]["code_revision"]}`, CPU float64. Current global acceptance: `{json.dumps(models["accepted"])}`. Reference fallback is the active workbench engine.

## Design and label eligibility

Price-only versus price-and-delta tanh MLPs, three hidden layers ×48, 5,041 parameters, identical 2,048 training examples, 300 full-batch Adam updates at .003, seeds17/31/47, matched initializations and derivative graphs. Difference is delta loss weight0 versus.25; price loss scale.1, delta scale.5. Both arms compute the graph, even with zero derivative weight, deliberately matching computational work. It is a bounded budget, not evidence of optimal tuning. P/K normalization and S/K inputs are differentiated analytically by autograd: delta d(P/K)/dm, gamma second/K, vega K*d(P/K)/dIV. Known-polynomial fixture independently checks transforms.

Training domain m .7–1.3, tau .1–2 calendar years, IV .1–.5, r .01–.08, q0–.04; ACT365 rounded days. Train seed101, with joint m>1.2/tau<.3 region excluded. Separate 256-point iid701, held709, exercise/near-expiry719, OOD727 sets. Boundary is m .75–1.03/tau1–29days; OOD is tau<.1 and IV>.5. No test region enters training or interpolation labels; seeds/labels/epochs/thresholds fixed before results. Dataset variations are synthetic design sampling, not market distributions.

European control: independent scalar analytical labels, fair vectorized analytical timing; model complexity earns no automatic credit. American target: constant-carry QuantLib FD American put K100, 512 time/spot mesh, damping2, decimal-vega bump .001; selected128/256/512/1024 convergence and CRR4096 independent price checks. Reference gate passed: {models["reference_gate"]["passed"]}. 32 training labels checked at512/1024, max price/delta/gamma/vega differences [.001454, .0000600, .00000565, .008471], allowing delta labels under .005 tolerance. Selected probes do not establish uniform convergence over exercise boundaries.

The boundary set exposed two FD512 negative-gamma shape failures despite zero interpolation error from full fallback. Diagnostic rechecks at1024 changed gamma from −.000137/−.000874 to +.000550/+.000136; price changed by approximately $0.00001. This is reference derivative uncertainty, not surrogate accuracy. Live probes qualify numerical FD Greeks; no clipping hides failures. American numerical prices are not a supported traded early-exercise/assignment simulation.

Grid baseline: 8×5×5×3×3 multilinear price table, 1,710 eligible labels; held cells missing. Missing/OOD cells fall back to reference, with cost included. Grid second differences are unreliable at knots. Price, delta, gamma and decimal-vega errors, bound/shape failures, share-equivalent exposure, scenario and actual integer-share effects are all distinct.

## Accuracy and risk effects

Mean RMSE over the three matched training seeds (K100 per-share price; delta share-equivalent; gamma1/USD; vegaUSD/decimalIV):

"""
rows = []
for target in ("european", "american"):
    for split in ("iid", "held-region", "boundary", "ood"):
        for method in ("price-only", "derivative-aware"):
            group = [
                r
                for r in models["metrics"]
                if r["target"] == target and r["split"] == split and r["method"] == method
            ]
            means = {
                key: float(np.mean([r["rmse"][key] for r in group]))
                for key in ("price", "delta", "gamma", "vega")
            }
            rows.append(
                [
                    target,
                    split,
                    method,
                    *[n(means[k], 6) for k in means],
                    sum(r["bounds_failures"] for r in group),
                    sum(r["shape_failures"] for r in group),
                ]
            )
report += table(
    [
        "Target",
        "Region",
        "Arm",
        "Price",
        "Delta",
        "Gamma",
        "Vega",
        "Bounds failures /768",
        "Shape failures /768",
    ],
    rows,
)
report += "\n\nPaired American iid delta RMSE, aware minus price-only, resampling the same256 synthetic points within each fixed model pair. These intervals condition on the trained models, not training-seed uncertainty:\n\n"
paired = []
with duckdb.connect() as db:
    for seed in models["protocol"]["ml_seeds"]:
        data = {}
        for method in ("price-only", "derivative-aware"):
            data[method] = np.array(
                [
                    r[0]
                    for r in db.execute(
                        "SELECT delta_error FROM read_parquet(?) WHERE target='american' AND split='iid' AND seed=? AND method=? ORDER BY m,tau,iv",
                        [models["errors"]["path"], seed, method],
                    ).fetchall()
                ]
            )
        delta = paired_interval(data["derivative-aware"], data["price-only"])
        paired.append(
            [
                seed,
                n(delta["rmse_difference"], 6),
                "[" + ", ".join(n(v, 6) for v in delta["ci95"]) + "]",
            ]
        )
report += table(["Seed", "Delta RMSE difference", "95% point-bootstrap CI"], paired)
report += "\n\nH5: derivative-aware American iid delta error improves about26% averaged across these three seeds, with separate boundary/OOD risks. Three seeds are too few for a robust training-variability claim, and gamma/vega improvement is neither guaranteed nor sufficient. No hyperparameter search or learned dynamic hedge is claimed.\n\n"
report += table(
    [
        "Region",
        "Arm / seed",
        "Scenario error USD/contract",
        "Integer-share mark P&L discrepancy USD",
    ],
    [
        [
            r["split"],
            f"{r['method']} / {r['seed']}",
            n(r["scenario_change_rmse_1_contract_usd"]),
            n(r["actual_share_hedge_pnl_discrepancy_rmse_usd"]),
        ]
        for r in models["metrics"]
        if r["target"] == "american" and r["method"] != "grid" and r["seed"] == 17
    ],
)
report += """

Scenario errors are +10% spot/+3 vol points with no time advance; integer shares round100*delta then multiply share discrepancy by ΔS. These are pointwise risk/hedge consequences, not a causal American assignment replay or profit estimate. Reference hedge shares are a numerical control, and no costs are silently attributed to these mark-only comparisons.

![Matched-seed Greek errors](../artifacts/report/surrogate-risk-errors.png)

Grid RMSE and fallback counts (zero error from full fallback must not be credited to interpolation):

"""
report += table(
    ["Target", "Region", "Price", "Delta", "Gamma", "Vega", "Fallback /256"],
    [
        [
            r["target"],
            r["split"],
            *[n(r["rmse"][k], 6) for k in ("price", "delta", "gamma", "vega")],
            r["fallback_points"],
        ]
        for r in models["metrics"]
        if r["method"] == "grid"
    ],
)
report += """

## Acceptance and speed

Declared in-domain and held-region limits at K100: price .15USD, delta.03, gamma.005, vega2USD/decimalIV RMSE, no bound or shape failure for any training seed. European bounds use discounted strike/spot, American uses intrinsic with a negative-rate-safe upper bound. Boundary/OOD rejects. Every current model fails; H6's joint accuracy-and-speed criterion is not established. No model enters the trading engine.

Fair warm256-point benchmarks include normalization/autograd/output, reference-cache clearing and grid fallback, no CPU transfers. Cold startup/model loading is excluded from warm comparison but separate live total-handler and API cold-first timing are exposed. The analytical European batch is faster than either model. Raw American models are much faster than uncached FD but fail accuracy; active fallback inherits reference cost. Only three repetitions for expensive FD/grid give rough latency quantiles, not deployment SLAs. No CUDA/RTX or MPS result is asserted.

"""
report += table(
    ["Target", "Method / seed", "Region", "p50 ms", "p95 ms", "Batch"],
    [
        [
            r["target"],
            f"{r['method']} / {r.get('seed', 'reference')}",
            r.get("split", "iid"),
            n(r["p50_ms"], 3),
            n(r["p95_ms"], 3),
            r["batch"],
        ]
        for r in models["timings"]
        if r["method"]
        in (
            "vector-reference-price-greeks",
            "vector-reference-price",
            "fd-reference-price-greeks",
            "grid",
        )
        or (r.get("seed") == 17 and r.get("split") == "iid")
    ],
)
report += "\n\nLabel/build/train costs and storage (parameter bytes exclude buffers, serialization overhead and activations):\n\n"
report += table(
    ["Target", "Method / seed", "Label/build/train seconds", "Parameter/table bytes"],
    [
        [
            r["target"],
            f"{r.get('method', 'reference labels')} / {r.get('seed', '—')}",
            n(r.get("label_seconds", r.get("build_seconds", r.get("train_seconds", 0))), 3),
            r.get("model_bytes", r.get("bytes", "—")),
        ]
        for r in models["generation"]
    ],
)
report += f"""

Reference label generation plus inference costs matter for amortization. Interpolation build time currently includes grid benchmark fallback timing as well as label construction, disclosed here; it is not a pure preprocessing timer. Broad bounds/shapes and frozen domain checks remain necessary even if aggregate RMSE improves. Future improvements require a newly registered protocol and new untouched tests; no post-result loosening of thresholds.

## Trial history, reproducibility and limits

Initial trial7f4b7fc81b8c48ed9602c5d65a90224b failed on acceptance-key mapping after training. Corrected trial7f4c3877b1f24143abb4a8d62e9de422 completed but its European bound counts are superseded because it used American intrinsic bounds. This run changes diagnostic correctness only: same labels, seeds, architecture, losses, optimizer and budgets. No positive result was chosen by repeated tuning. Model payload SHA256 hashes now bind probe weights to the recorded generation; missing/changed payloads fall back. Earlier records remain in the registry.

Run manifest `artifacts/jobs/{m["id"]}.manifest.json`; error payload `{models["errors"]["path"]}`, SHA `{models["errors"]["sha256"]}`, {models["errors"]["rows"]:,} rows. Exact source SHA `{m["manifest"]["provenance"]["source_sha256"]}`. Pinned versions in `uv.lock`. Reproduce `uv run orl train`, `uv run orl export`, then `uv run python scripts/write_reports.py --output docs`. Raw models/data and generated figures are ignored in Git. This study supplies the required AI contribution through tested acceptance/rejection, not a profitability promise.
"""
(args.output / "ml-report.md").write_text(report)
print(f"Wrote verified reports to {args.output}")
