"""Inspect option prices and a finite stress before running a full study."""

import json

from options_risk_lab.pricing import bsm
from options_risk_lab.services import WorkbenchRequest, portfolio_view


def main() -> None:
    for kind in ("call", "put"):
        result = bsm(100, 100, 1, 0.2, 0.05, 0, kind)
        print(f"{kind}: {result.model_dump_json()}")
    portfolio = portfolio_view(WorkbenchRequest())
    print("Default short-straddle book: one short call, one short put and 27 shares.")
    print(json.dumps(portfolio["grid"][-1], indent=2))


if __name__ == "__main__":
    main()
