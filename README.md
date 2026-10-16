# Options Risk Lab

[![Tests](https://github.com/tomccrook/options-risk-lab/actions/workflows/tests.yml/badge.svg)](https://github.com/tomccrook/options-risk-lab/actions/workflows/tests.yml)

**A portfolio can have almost zero delta and still lose money.** This project follows that gap from option prices and Greeks through finite market moves, feasible hedge trades and a cash account.

[Interactive demo](https://tomcrook.dev/demos/options-risk) · [Project study](https://tomcrook.dev/projects/options-risk) · [Model-risk report](docs/model-risk-report.md)

The Python library combines independently checked pricing engines, signed option portfolios, scenario repricing, integer hedge selection and a causal hedge ledger. A separate PyTorch study asks whether learning both prices and derivatives produces a reliable pricing surrogate.

## Try a small example

Use Python 3.14.8 and [uv](https://docs.astral.sh/uv/getting-started/installation/). Dependencies are locked in `uv.lock`.

```bash
uv sync --locked
uv run python examples/price_and_stress.py
uv run orl price
uv run orl shock
uv run python -m pytest
```

The example prices a European call and put, then reprices the default short-straddle portfolio after a 30-day market move. It uses synthetic inputs, needs no market-data account and does not launch a full evaluation.

To open the local workbench, use Node 24.21.0 and two terminals:

```bash
npm ci --prefix apps/web
uv run uvicorn options_risk_lab.api:app --host 127.0.0.1 --port 8000
```

```bash
npm run dev --prefix apps/web
```

Open `http://127.0.0.1:5173`. Prices and small scenario calculations work immediately. Full evaluation panels require explicitly generated runs. See [reproduction](docs/reproduction.md) before starting the larger jobs.

## Three models, two different questions

| Model | Assumption | Pricing method |
|---|---|---|
| Black–Scholes–Merton | Continuous price moves with fixed volatility. | Analytical European formula, with independent reference and finite-difference checks. |
| Merton jump diffusion | Continuous moves plus occasional random jumps. | Controlled Poisson mixture, checked against independent Fourier integration. |
| Heston | Random, mean-reverting variance correlated with the share price. | Characteristic-function integration with refinement and QuantLib checks. |

Comparing models tests assumptions about risk. Comparing Monte Carlo with a reference formula tests a numerical calculation under one model. Those are different questions. Fitting the same initial option premium also leaves different deltas and hedge requirements.

## Results worth examining

- **Local sensitivity is not a finite-move hedge.** In the recorded example, a short call and put with a 27-share delta hedge lost $771.07 under a 20% price rise, a five-point volatility rise and 30 days passing.
- **A richer model does not automatically give a better stock hedge.** In the Heston market, ordinary Heston delta had $540.07 financed-error RMSE versus $464.25 for fixed-volatility BSM. A separate covariance-adjusted Heston stock hedge reduced that error to $417.37. Under the Merton market, Merton delta did not beat BSM.
- **Better learned derivatives were insufficient.** Derivative-aware training improved one American-put delta comparison, but every tested target/training arm failed the complete risk gates. Numerical reference engines remain active.

These are results from completed synthetic studies, conditional on their costs, execution delay and parameter assumptions. They are not trading returns. The [research report](docs/research-report.md), [model-risk report](docs/model-risk-report.md) and [surrogate report](docs/ml-report.md) retain the adverse results and uncertainty.

## Where to inspect the implementation

| Question | Code |
|---|---|
| Are the prices and units right? | [`pricing.py`](src/options_risk_lab/pricing.py), [`models.py`](src/options_risk_lab/models.py), [`reference.py`](src/options_risk_lab/reference.py) |
| What does a finite market move do to the book? | [`risk.py`](src/options_risk_lab/risk.py), [`hedging.py`](src/options_risk_lab/hedging.py) |
| Did the trade actually pay for its hedge? | [`ledger.py`](src/options_risk_lab/ledger.py), [`simulation.py`](src/options_risk_lab/simulation.py), [`model_replay.py`](src/options_risk_lab/model_replay.py) |
| Was the evaluation protected from tuning? | [`evaluation.py`](src/options_risk_lab/evaluation.py), [`model_evaluation.py`](src/options_risk_lab/model_evaluation.py), [`configs`](configs) |
| Can the learned approximation be trusted? | [`ml.py`](src/options_risk_lab/ml.py), [`tests/test_ml.py`](tests/test_ml.py) |

## Verification and scope

```bash
uv run python scripts/dependency_smoke.py
uv run ruff check src tests scripts
uv run mypy src
uv run python -m pytest
npm run build --prefix apps/web
```

Tests cover parity, bounds, independent numerical references, hedge feasibility, cash reconciliation, delayed fills, causal information and rejected surrogate gates. CI runs bounded checks, not the full research programme.

The main book is European, cash-settled, in USD and on one synthetic underlying. American puts are a separate numerical/learning target. Market calibration, liquidity, borrow and real execution are outside the evidence here. Raw research runs, checkpoints and local databases are excluded from the source release. See [release notes](docs/public-release.md).
