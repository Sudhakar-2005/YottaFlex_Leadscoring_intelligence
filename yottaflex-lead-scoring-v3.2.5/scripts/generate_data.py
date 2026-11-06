"""Generate data pipeline + exports (P0-C).

Usage:
    python scripts/generate_data.py --scale full
    python scripts/generate_data.py --scale starter --out data/starter_exports
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yottaflex.config import (  # noqa: E402
    AnomalyInjectionConfig,
    AnomalyQuotas,
    CountsConfig,
    DuplicatesConfig,
    load_settings,
)
from yottaflex.pipeline import run_full_pipeline  # noqa: E402

STARTER_COUNTS = dict(
    companies=500,
    contacts=1000,
    leads=2000,
    opportunities=300,
    campaigns=10,
    sales_reps=20,
    territories=16,
    products=10,
)
STARTER_DUPLICATES = dict(
    natural_duplicate_companies=6,
    natural_duplicate_contacts=15,
    natural_duplicate_leads=40,
    natural_duplicate_opportunities=2,
)
STARTER_QUOTAS = dict(
    opted_out_contacted=2,
    temporal_leakage=2,
    territory_mismatch=2,
    duplicate_opportunity=1,
    stage_history_gap=2,
)


def build_settings(scale: str, seed: int | None, database_url: str | None):
    s = load_settings()
    if scale == "starter":
        s = s.model_copy(
            update={
                "counts": CountsConfig(
                    **{**s.counts.model_dump(), **STARTER_COUNTS}
                ),
                "duplicates": DuplicatesConfig(**STARTER_DUPLICATES),
                "anomaly_injection": AnomalyInjectionConfig(
                    enabled=s.anomaly_injection.enabled,
                    quotas=AnomalyQuotas(**STARTER_QUOTAS),
                ),
            }
        )
    if seed is not None:
        s = s.model_copy(update={"seed": seed})
    if database_url is not None:
        s = s.model_copy(update={"database_url": database_url})
    return s


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", choices=["starter", "full"], default="full")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--no-inject", action="store_true")
    parser.add_argument(
        "--export-dir",
        default=None,
        help="explicit export destination (default: data/generated/exports)",
    )
    parser.add_argument(
        "--overwrite-exports",
        action="store_true",
        help="allow overwriting an existing export set (required for destructive export writes)",
    )
    args = parser.parse_args()

    settings = build_settings(args.scale, args.seed, args.database_url)
    result = run_full_pipeline(
        settings=settings,
        database_url=args.database_url,
        inject_anomalies=not args.no_inject,
        write_reports=True,
        export_dir=args.export_dir,
        overwrite_exports=args.overwrite_exports,
    )
    steps = result.steps
    print("generate: OK")
    print(f"scale: {args.scale}, seed: {settings.seed}")
    print(f"opportunities: {steps.get('opportunities')}")
    print(f"injected: {steps.get('injected')}")
    print(f"baseline_exceptions: {steps.get('baseline_exceptions')}")
    print(f"exceptions: {steps.get('exceptions')}")
    ev = steps.get("exception_evaluation") or {}
    print(
        f"evaluation P/R/F1: {ev.get('overall_precision')} / "
        f"{ev.get('overall_recall')} / {ev.get('overall_f1')}"
    )
    exp = steps.get("export") or {}
    print(
        f"exports written: {len(exp.get('files', {}))} files under "
        f"{steps.get('export_dir', 'data/exports')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
