from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_SETTINGS_PATH = CONFIG_DIR / "settings.yaml"
DEFAULT_SCORE_RULES_PATH = CONFIG_DIR / "score_rules.yaml"

_SQLITE_URL_RE = re.compile(r"^sqlite:///(?P<path>.+)$", re.IGNORECASE)
_WINDOWS_ABS_RE = re.compile(r"^/[A-Za-z]:[/\\]")


def canonical_sqlite_path(url: str) -> str | None:
    """Canonical absolute filesystem path for a SQLite URL, or None.

    Handles (V3.2.2 path-normalization hardening):
      - scheme case differences (SQLite:///...)
      - URL-escaped characters (%20)
      - ``/./`` and ``/../`` segments and duplicate separators
      - backslashes vs forward slashes
      - three-slash relative, three-slash drive-absolute, four-slash absolute
      - Windows case-insensitivity (normcase) and trailing dot/space aliasing

    Returns a normalized, lower-cased (on Windows) absolute path string so that
    equivalent representations compare equal. Non-SQLite URLs and ``:memory:``
    return None (callers fall back to string comparison).
    """
    m = _SQLITE_URL_RE.match(str(url).strip())
    if not m:
        return None
    raw = unquote(m.group("path"))
    if raw in (":memory:", ""):
        return None
    if os.name == "nt" and _WINDOWS_ABS_RE.match(raw):
        raw = raw[1:]  # "/C:/x" -> "C:/x"
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    try:
        p = p.resolve()
    except OSError:
        p = Path(os.path.abspath(str(p)))
    s = os.path.normcase(str(p))
    if os.name == "nt":
        s = s.rstrip(" .")  # Win32 drops trailing dot/space on the final component
    return s


class ScoringWeights(BaseModel):
    fit: float = 0.40
    intent: float = 0.35
    engagement: float = 0.25

    @field_validator("fit", "intent", "engagement")
    @classmethod
    def _non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("weights must be >= 0")
        return v

    def validate_sum(self) -> None:
        total = self.fit + self.intent + self.engagement
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"scoring weights must sum to 1.0, got {total}")


class CategoryThresholds(BaseModel):
    hot: int = 80
    warm: int = 60
    nurture: int = 40


class ScoringConfig(BaseModel):
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    category_thresholds: CategoryThresholds = Field(default_factory=CategoryThresholds)
    dimension_caps: dict[str, int] = Field(
        default_factory=lambda: {"fit": 100, "intent": 100, "engagement": 100}
    )


class CountsConfig(BaseModel):
    companies: int = 5000
    contacts: int = 10000
    leads: int = 20000
    opportunities: int = 3000
    campaigns: int = 30
    sales_reps: int = 80
    territories: int = 16
    products: int = 10


class RoutingConfig(BaseModel):
    assignment_strategy: str = "least_loaded_then_id"


class TasksConfig(BaseModel):
    due_days: dict[str, int] = Field(
        default_factory=lambda: {
            "hot": 1,
            "warm": 3,
            "nurture": 7,
            "cold": 14,
        }
    )
    hot_task_type: str = "demo"
    warm_task_type: str = "call"
    nurture_task_type: str = "email"
    cold_task_type: str = "email"
    cold_create_task: bool = True


class ConsentConfig(BaseModel):
    email_grant_rate: float = 0.88
    phone_grant_rate: float = 0.75
    revoke_rate_of_granted: float = 0.10


class DuplicatesConfig(BaseModel):
    """Natural baseline duplicate volumes (P0-B).

    These are real-world-like duplicate records generated inside the valid
    baseline (soft-dedup marks them; originals preserved). Deliberately
    injected anomaly duplicates are controlled separately by
    anomaly_injection.quotas and labelled origin='injected'.
    """

    natural_duplicate_companies: int = 60
    natural_duplicate_contacts: int = 150
    natural_duplicate_leads: int = 400
    natural_duplicate_opportunities: int = 15


class EvaluationConfig(BaseModel):
    """Held-out evaluation methodology (P0-D)."""

    heldout_fraction: float = 0.30

    @field_validator("heldout_fraction")
    @classmethod
    def _valid(cls, v: float) -> float:
        if not 0.0 <= v < 1.0:
            raise ValueError("heldout_fraction must be in [0, 1)")
        return v


class OpportunitySelectionConfig(BaseModel):
    """Documented business factors for opportunity selection.

    The final lead_score / lead_category must NOT be used here (P0-D).
    Weights describe independent conversion-propensity inputs.
    """

    intent_weight: float = 0.15
    engagement_weight: float = 0.10
    budget_weight: float = 0.25
    fit_weight: float = 0.10
    followup_weight: float = 0.15
    jitter_weight: float = 0.25


class OpportunityOutcomeConfig(BaseModel):
    """Documented business factors for won/lost/open outcomes.

    lead_score must NOT be used (P0-D). open_rate is the fraction of
    opportunities deliberately left open (demo/proposal) for pipeline realism.
    """

    open_rate: float = 0.15
    # win-probability factor contributions (sum of maxima + base <= 1.0)
    base_win_p: float = 0.20
    fit_max: float = 0.20
    intent_max: float = 0.25
    budget_max: float = 0.15
    followup_max: float = 0.10
    engagement_max: float = 0.10

    @field_validator("open_rate")
    @classmethod
    def _valid_open(cls, v: float) -> float:
        if not 0.0 <= v <= 0.5:
            raise ValueError("open_rate must be in [0, 0.5]")
        return v


class AnomalyQuotas(BaseModel):
    opted_out_contacted: int = 20
    temporal_leakage: int = 15
    territory_mismatch: int = 15
    duplicate_opportunity: int = 10
    stage_history_gap: int = 15


class AnomalyInjectionConfig(BaseModel):
    enabled: bool = True
    quotas: AnomalyQuotas = Field(default_factory=AnomalyQuotas)


class AnalyticsConfig(BaseModel):
    eligibility_excluded_statuses: list[str] = Field(
        default_factory=lambda: ["disqualified", "opted_out"]
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    seed: int = 20261022
    base_datetime: str = "2025-01-01T00:00:00+00:00"
    database_url: str = "sqlite:///data/yottaflex.db"
    business_id_year: int = 2026
    counts: CountsConfig = Field(default_factory=CountsConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    tasks: TasksConfig = Field(default_factory=TasksConfig)
    consent: ConsentConfig = Field(default_factory=ConsentConfig)
    duplicates: DuplicatesConfig = Field(default_factory=DuplicatesConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    opportunity_selection: OpportunitySelectionConfig = Field(
        default_factory=OpportunitySelectionConfig
    )
    opportunity_outcomes: OpportunityOutcomeConfig = Field(
        default_factory=OpportunityOutcomeConfig
    )
    anomaly_injection: AnomalyInjectionConfig = Field(
        default_factory=AnomalyInjectionConfig
    )
    analytics: AnalyticsConfig = Field(default_factory=AnalyticsConfig)

    @classmethod
    def from_yaml(cls, path: Path | str = DEFAULT_SETTINGS_PATH) -> Settings:
        with open(path, encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return cls(**raw)

    def base_dt(self) -> datetime:
        """Base timestamp as naive UTC for consistent DB storage/compare."""
        from datetime import datetime as _dt

        dt = _dt.fromisoformat(self.base_datetime)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt

    def resolved_database_url(self) -> str:
        url = self.database_url
        if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
            rel = url.removeprefix("sqlite:///")
            abs_path = (PROJECT_ROOT / rel).resolve()
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{abs_path.as_posix()}"
        return url


def load_settings(path: Path | str | None = None) -> Settings:
    if path is None:
        return Settings.from_yaml()
    return Settings.from_yaml(path)


def load_score_rules(path: Path | str = DEFAULT_SCORE_RULES_PATH) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return list(data.get("rules", []))
