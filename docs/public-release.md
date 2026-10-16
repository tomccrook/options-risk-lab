# Public source release

This is a reviewed source snapshot first published on 16 October 2026. The original research checkout and its history remain separate. The public history was subsequently reorganised into topical import commits with earlier author dates. Those dates were assigned during reconstruction; they are not verified dates of development or evidence that the projects were complete before September. Committer timestamps retain the actual import date, and each import commit identifies the reconstruction in its message.

The source includes independent pricing controls, risk/hedge calculations, the cash ledger, simulation, protected evaluation, the surrogate experiment, tests and the local web workbench. It excludes training weights, raw run directories, job databases, machine setup records and private career notes.

The small example calls the existing pricing and portfolio services. It does not replace the scientific study or change the reported numerical evidence. Archived result tables describe the original completed runs; generated figures and report exports can be recreated locally.

The verification below applies to this release checkout, rather than relying on earlier recorded checks.

## Release verification — 16 October 2026

51 tests passed on CPython 3.14.8. The price/stress example reproduced the recorded default scenario. Ruff and mypy checks passed.

Dependency locks were installed into separate environments. The source-publication review checked the selected file list, private paths, credential patterns, excluded data/weight formats and historical defensive outputs. These checks do not rerun the full protected scientific studies. Upstream dependency deprecation warnings remain visible in test output.

The local frontend production build passed with Node 24.21.0. The GitHub Actions workflow includes Python checks and frontend compilation; hosted-run status is separate from these local results.

## Reconstructed import schedule

| Assigned author date | Imported component |
| --- | --- |
| 2025-12-28 | Set up the options research package |
| 2026-02-07 | Import European and American pricing controls |
| 2026-03-18 | Add portfolio risk and stress calculations |
| 2026-06-07 | Track hedges and financing cash flows |
| 2026-06-19 | Import path simulation and alternative pricing models |
| 2026-07-04 | Add protected evaluation and surrogate learning |
| 2026-07-27 | Expose pricing services and research reports |
| 2026-08-09 | Set up the browser workbench |
| 2026-08-29 | Add model and hedge inspection views |
| 2026-09-12 | Document findings and runnable reproduction |

The source import is consolidated into ten substantive file groups. Subsequent maintenance changes use their actual dates.
