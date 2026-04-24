"""Pydantic session-state models.

The shape mirrors `scheduler.persistence.dump_state`/`load_state` so a YAML
round-trip is lossless, but exposes list-typed fields (instead of
comma-separated strings) for a nicer SPA API. Adapters in `api.sessions`
handle the list↔CSV conversion when calling the v1 scheduler code.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BlockType = Literal[
    "Leave", "No on-call", "No AM", "No PM", "Prefer AM", "Prefer PM"
]
Tier = Literal["junior", "senior", "consultant"]
Session = Literal["AM", "PM", "FULL_DAY"]


def _split_csv(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return []


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class DoctorEntry(StrictModel):
    name: str
    tier: Tier
    subspec: str | None = None
    eligible_stations: list[str] = Field(default_factory=list)
    prev_workload: int = 0
    fte: float = 1.0
    max_oncalls: int | None = None

    @field_validator("eligible_stations", mode="before")
    @classmethod
    def _coerce_stations(cls, v: Any) -> list[str]:
        return _split_csv(v)

    @field_validator("subspec", mode="before")
    @classmethod
    def _blank_subspec(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


class StationEntry(StrictModel):
    name: str
    sessions: list[Session] = Field(default_factory=lambda: ["AM", "PM"])
    required_per_session: int = 1
    eligible_tiers: list[Tier] = Field(default_factory=list)
    is_reporting: bool = False

    @field_validator("sessions", mode="before")
    @classmethod
    def _coerce_sessions(cls, v: Any) -> list[str]:
        items = [x.upper() for x in _split_csv(v)]
        # FULL_DAY is mutually exclusive with AM/PM — if both are
        # specified, FULL_DAY wins (it's the more specific intent).
        if "FULL_DAY" in items:
            return ["FULL_DAY"]
        cleaned = [x for x in items if x in ("AM", "PM")]
        return cleaned or ["AM", "PM"]

    @field_validator("eligible_tiers", mode="before")
    @classmethod
    def _coerce_tiers(cls, v: Any) -> list[str]:
        return [x.lower() for x in _split_csv(v)
                if x.lower() in ("junior", "senior", "consultant")]


class BlockEntry(StrictModel):
    doctor: str
    date: date
    end_date: date | None = None
    type: BlockType


class OverrideEntry(StrictModel):
    doctor: str
    date: date
    role: str  # STATION_<name>_<AM|PM> | ONCALL | WEEKEND_EXT | WEEKEND_CONSULT


class TierLabels(StrictModel):
    junior: str = "Junior"
    senior: str = "Senior"
    consultant: str = "Consultant"


class ShiftLabels(StrictModel):
    """Human-readable labels for the internal session keys.

    The solver reasons over AM / PM / FULL_DAY / ONCALL / EXT /
    WCONSULT — these labels are cosmetic, used by the UI when it wants
    to say "Morning 07:00–15:00" instead of "AM" in the Roster grid,
    Export preview, and mailto body. Changing them does NOT change
    solver behaviour. Defaults match the historic names so existing
    exports stay unchanged.
    """

    am: str = "AM"
    pm: str = "PM"
    full_day: str = "Full day"
    oncall: str = "Night call"
    weekend_ext: str = "Weekend extended"
    weekend_consult: str = "Weekend consultant"


class Horizon(StrictModel):
    # Defaults to today so the date picker on the SPA lands on a usable value
    # instead of a blank calendar on first load.
    start_date: date | None = Field(default_factory=date.today)
    n_days: int = 21
    public_holidays: list[date] = Field(default_factory=list)


class SoftWeights(StrictModel):
    workload: int = 40
    sessions: int = 5
    oncall: int = 10
    weekend: int = 10
    reporting: int = 5
    idle_weekday: int = 100
    preference: int = 5


class WorkloadWeights(StrictModel):
    weekday_session: int = 10
    weekend_session: int = 15
    weekday_oncall: int = 20
    weekend_oncall: int = 35
    weekend_ext: int = 20
    weekend_consult: int = 25


class Hours(StrictModel):
    weekday_am: float = 4.0
    weekday_pm: float = 4.0
    weekend_am: float = 4.0
    weekend_pm: float = 4.0
    weekday_oncall: float = 12.0
    weekend_oncall: float = 16.0
    weekend_ext: float = 12.0
    weekend_consult: float = 8.0


class ConstraintsConfig(StrictModel):
    h4_enabled: bool = True
    h4_gap: int = 3
    h5_enabled: bool = True
    h6_enabled: bool = True
    h7_enabled: bool = True
    h8_enabled: bool = True
    h9_enabled: bool = True
    h11_enabled: bool = True
    weekend_am_pm: bool = False
    # Default on so Minimal-staffing mode still produces an on-call-covered
    # roster every weekday night.
    weekday_oncall_coverage: bool = True


class SolverSettings(StrictModel):
    time_limit: int = 60
    num_workers: int = 8
    feasibility_only: bool = False


class SessionState(StrictModel):
    schema_version: int = 1
    horizon: Horizon = Field(default_factory=Horizon)
    doctors: list[DoctorEntry] = Field(default_factory=list)
    stations: list[StationEntry] = Field(default_factory=list)
    blocks: list[BlockEntry] = Field(default_factory=list)
    overrides: list[OverrideEntry] = Field(default_factory=list)
    tier_labels: TierLabels = Field(default_factory=TierLabels)
    shift_labels: ShiftLabels = Field(default_factory=ShiftLabels)
    subspecs: list[str] = Field(default_factory=lambda: ["Neuro", "Body", "MSK"])
    soft_weights: SoftWeights = Field(default_factory=SoftWeights)
    workload_weights: WorkloadWeights = Field(default_factory=WorkloadWeights)
    hours: Hours = Field(default_factory=Hours)
    constraints: ConstraintsConfig = Field(default_factory=ConstraintsConfig)
    solver: SolverSettings = Field(default_factory=SolverSettings)
