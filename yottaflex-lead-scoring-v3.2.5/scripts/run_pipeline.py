from __future__ import annotations

import argparse
import json
import sys

from yottaflex.config import load_settings
from yottaflex.pipeline import run_full_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run YottaFlex full pipeline")
    parser.add_argument("--no-inject", action="store_true", help="Skip anomaly injection")
    parser.add_argument("--db", default=None, help="Override database URL")
    parser.add_argument("--mini", action="store_true", help="Use mini dataset for smoke runs")
    args = parser.parse_args()

    settings = load_settings()
    if args.mini:
        settings.counts.companies = 80
        settings.counts.contacts = 120
        settings.counts.leads = 200
        settings.counts.opportunities = 40
        settings.counts.campaigns = 8
        settings.counts.sales_reps = 16

    result = run_full_pipeline(
        settings=settings,
        database_url=args.db,
        inject_anomalies=not args.no_inject,
    )
    print(json.dumps(result.steps, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
