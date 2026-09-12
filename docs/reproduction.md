# Reproducing calculations and studies

The default example, pricing commands and tests are the quickest way to inspect the numerical and accounting choices. They do not require saved study outputs.

```bash
uv sync --locked
uv run python scripts/dependency_smoke.py
uv run python examples/price_and_stress.py
uv run orl models
uv run python -m pytest
```

The full studies are explicit, longer-running commands. They produce run manifests, result hashes and output files under ignored `artifacts/`:

```bash
uv run orl evaluate --phase development
uv run orl evaluate --phase locked
uv run orl train
uv run orl export
uv run orl model-evaluate --phase development
uv run orl model-evaluate --phase locked
uv run orl model-export
```

Read the [experiment design](experiments.md) and [model-risk report](model-risk-report.md) before running these. A reproduction of previously examined test data is not a new blind test. Register fresh choices and seeds before using new results to support a new claim.

The report-writing scripts generate local tables and figures. Large research output directories and trained weights are not part of the public source repository. Archived report text describes the original completed study; references to generated files mean local outputs, not hosted downloads.

The source is locked to Python 3.14 and the recorded `.python-version` selects 3.14.8. The frontend's `.node-version` selects Node 24.21.0. A failed exact-runtime installation should be investigated rather than silently changing dependency versions and calling the result an exact reproduction.
