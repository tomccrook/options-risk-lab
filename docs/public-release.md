# Public source release

This repository publishes a reviewed source snapshot of the local Options Risk Lab. Its new commits record the actual publication work. The original checkout, its commits and its generated research outputs are retained separately.

The source includes independent pricing controls, risk/hedge calculations, the cash ledger, simulation, protected evaluation, the surrogate experiment, tests and the local web workbench. It excludes training weights, raw run directories, job databases, machine setup records and private career notes.

The small example calls the existing pricing and portfolio services. It does not replace the scientific study or change the reported numerical evidence. Archived result tables describe the original completed runs; generated figures and report exports can be recreated locally.

The verification below applies to this release checkout, rather than relying on earlier recorded checks.

## Release verification — 16 October 2026

51 tests passed on CPython 3.14.8. The price/stress example reproduced the recorded default scenario. Ruff and mypy checks passed.

Dependency locks were installed into separate environments. The source-publication review checked the selected file list, private paths, credential patterns, excluded data/weight formats and historical defensive outputs. These checks do not rerun the full protected scientific studies. Upstream dependency deprecation warnings remain visible in test output.

The local frontend production build passed with Node 24.21.0. The GitHub Actions workflow includes Python checks and frontend compilation; hosted-run status is separate from these local results.
