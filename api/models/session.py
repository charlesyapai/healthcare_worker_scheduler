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
Weekday = Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_ALL: tuple[Weekday, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
WEEKDAYS_WEEKDAY: tuple[Weekday, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri")
WEEKDAYS_WEEKEND: tuple[Weekday, ...] = ("Sat", "Sun")
# Phase B: legacy role aliases on default OnCallType keys. Lets pre-Phase-B
# scenarios continue emitting `ONCALL` / `WEEKEND_EXT` / `WEEKEND_CONSULT`
# role strings unchanged after migration.
LegacyRoleAlias = Literal["ONCALL", "WEEKEND_EXT", "WEEKEND_CONSULT"]


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
    eligible_stations: list[str] = Field(default_factory=list)
    # Phase B: per-doctor on-call eligibility, keyed by OnCallType.key.
    # Empty list = doctor is not eligible for any on-call type. Migration
    # of v2 sessions populates this from `OnCallType.eligible_tiers`.
    eligible_oncall_types: list[str] = Field(default_factory=list)
    prev_workload: int = 0
    fte: float = 1.0
    max_oncalls: int | None = None

    @field_validator("eligible_stations", mode="before")
    @classmethod
    def _coerce_stations(cls, v: Any) -> list[str]:
        return _split_csv(v)

    @field_validator("eligible_oncall_types", mode="before")
    @classmethod
    def _coerce_oncall_types(cls, v: Any) -> list[str]:
        return _split_csv(v)


class StationEntry(StrictModel):
    name: str
    sessions: list[Session] = Field(default_factory=lambda: ["AM", "PM"])
    required_per_session: int = 1
    # Advisory metadata: hints to the UI about which tiers usually staff this
    # station. NOT enforced as a hard rule by the solver — per-doctor
    # eligible_stations is the only enforced eligibility check. Kept so the
    # Stations editor can pre-fill new doctors' eligibility lists.
    eligible_tiers: list[Tier] = Field(default_factory=list)
    is_reporting: bool = False
    # Per-station weekday / weekend gate. Replaces the old global
    # constraints.weekend_am_pm flag. Default: weekday-only (matches the
    # historical default for AM/PM stations).
    weekday_enabled: bool = True
    weekend_enabled: bool = False

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


class RolePreferenceEntry(StrictModel):
    """A doctor's preference for a particular role, expressed as a
    minimum allocation target over the horizon with a priority weight.

    `role` is either:
      * a station name (e.g. "CT", "MR") — counts AM + PM allocations at
        that station, regardless of session side;
      * one of the literal non-station roles: "ONCALL", "WEEKEND_EXT",
        "WEEKEND_CONSULT".

    The solver adds a soft shortfall penalty
    ``priority × max(0, min_allocations − actual)`` to the objective, so
    a higher-priority preference is more costly to under-deliver. This
    is a bias, not a hard guarantee — if the preference can't be met
    without breaking H1/H2/H8 the solver will still ship a roster and
    let the shortfall show in the audit.
    """

    doctor: str
    role: str
    min_allocations: int = Field(default=1, ge=1, le=90)
    priority: int = Field(default=5, ge=1, le=10)


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


class OnCallType(StrictModel):
    """User-defined on-call shift type.

    Replaces the hard-baked `oncall` / `ext` / `wconsult` variable
    families with a single generic family. The solver creates a
    `oc_<key>[d, day]` indicator variable for each (doctor, active-day)
    pair. Constraints apply per-type:

    * **daily_required** — number of doctors required to fill this
      on-call type each `days_active` day.
    * **next_day_off** — if True, no station/on-call work the day
      after a fill (post-shift rest). Generalises legacy H5.
    * **frequency_cap_days** — sliding 1-in-N cap; None = uncapped.
      Generalises legacy H4.
    * **works_full_day** — if True, the on-call doctor does no
      AM/PM station work that day (legacy H6 senior pattern).
    * **works_pm_only** — if True, the on-call doctor must work the
      PM session that day (legacy H7 junior pattern).
    * **counts_as_weekend_role** — if True, every assignment is bucketed
      as weekend work for fairness (S3). If False, only assignments on
      calendar weekend days count as weekend.
    * **legacy_role_alias** — when set, the emitted role string is the
      alias literal (e.g. `ONCALL`) instead of `ONCALL_<key>`. Used by
      migration so existing scenarios keep producing the same role
      strings post-Phase-B.

    `start_hour` / `end_hour` are advisory clock-time hints (cosmetic
    until Phase D). Currently used by the UI for display + by the
    fairness bucket if the type spans midnight.
    """

    key: str
    label: str = ""
    start_hour: int = Field(default=20, ge=0, le=23)
    end_hour: int = Field(default=8, ge=0, le=23)
    days_active: list[Weekday] = Field(default_factory=lambda: list(WEEKDAY_ALL))
    eligible_tiers: list[Tier] = Field(default_factory=list)
    daily_required: int = Field(default=1, ge=0)
    post_shift_rest_hours: int = Field(default=11, ge=0)
    next_day_off: bool = True
    frequency_cap_days: int | None = 3
    counts_as_weekend_role: bool = False
    works_full_day: bool = False
    works_pm_only: bool = False
    legacy_role_alias: LegacyRoleAlias | None = None

    @field_validator("days_active", mode="before")
    @classmethod
    def _coerce_days(cls, v: Any) -> list[str]:
        items = _split_csv(v)
        # Capitalise + filter to known weekdays so legacy CSV / lower-case
        # entries normalise. Anything not in WEEKDAY_ALL is dropped silently.
        cleaned: list[str] = []
        for x in items:
            cap = x[:1].upper() + x[1:].lower()
            if cap in WEEKDAY_ALL:
                cleaned.append(cap)
        return cleaned

    @field_validator("eligible_tiers", mode="before")
    @classmethod
    def _coerce_tiers(cls, v: Any) -> list[str]:
        return [x.lower() for x in _split_csv(v)
                if x.lower() in ("junior", "senior", "consultant")]


class ConstraintsConfig(StrictModel):
    """Phase B: most legacy on-call toggles are now per-OnCallType. The
    only global constraint flags that survive are statutory rest
    (`h5_enabled` — master override of every type's `next_day_off`),
    weekend lieu day (`h9_enabled`, applies to types with
    `counts_as_weekend_role=True`), and the idle-weekday penalty
    (`h11_enabled`, soft S5)."""

    h5_enabled: bool = True
    h9_enabled: bool = True
    h11_enabled: bool = True


class SolverSettings(StrictModel):
    time_limit: int = 60
    num_workers: int = 8
    feasibility_only: bool = False


class SessionState(StrictModel):
    schema_version: int = 3
    horizon: Horizon = Field(default_factory=Horizon)
    doctors: list[DoctorEntry] = Field(default_factory=list)
    stations: list[StationEntry] = Field(default_factory=list)
    blocks: list[BlockEntry] = Field(default_factory=list)
    overrides: list[OverrideEntry] = Field(default_factory=list)
    role_preferences: list[RolePreferenceEntry] = Field(default_factory=list)
    tier_labels: TierLabels = Field(default_factory=TierLabels)
    shift_labels: ShiftLabels = Field(default_factory=ShiftLabels)
    on_call_types: list[OnCallType] = Field(default_factory=list)
    soft_weights: SoftWeights = Field(default_factory=SoftWeights)
    workload_weights: WorkloadWeights = Field(default_factory=WorkloadWeights)
    hours: Hours = Field(default_factory=Hours)
    constraints: ConstraintsConfig = Field(default_factory=ConstraintsConfig)
    solver: SolverSettings = Field(default_factory=SolverSettings)
