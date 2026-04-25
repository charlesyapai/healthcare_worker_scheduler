"""Problem-instance data classes and a synthetic generator.

The synthetic generator produces realistic-shaped instances for benchmarking
without needing real hospital data. Tier mix, station list, and leave rates
match the defaults documented in `docs/CONSTRAINTS.md §5`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

TIERS = ("junior", "senior", "consultant")
# Internal session keys the CP-SAT model reasons over. FULL_DAY stations
# are unpacked by the model into paired AM+PM variables (see
# scheduler/model.py) so constraints that count AM/PM separately keep
# working — FULL_DAY is a UX shorthand for "book both halves of the day".
SESSIONS = ("AM", "PM")
FULL_DAY = "FULL_DAY"
# Calendar-day labels for OnCallType.days_active. Indices match Python's
# date.weekday() convention (Mon=0 .. Sun=6).
WEEKDAY_NAMES: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True)
class Station:
    name: str
    sessions: tuple[str, ...]
    required_per_session: int
    # Advisory metadata only — the solver does not gate eligibility on
    # this; per-doctor `eligible_stations` is the only enforced check.
    eligible_tiers: frozenset[str]
    is_reporting: bool = False
    # Per-station weekday / weekend gate. Weekday-only is the historical
    # default. Replaces the old global `Instance.weekend_am_pm_enabled`.
    weekday_enabled: bool = True
    weekend_enabled: bool = False


@dataclass(frozen=True)
class OnCallType:
    """Solver-side mirror of the Pydantic `OnCallType` model.

    Generic on-call shift type. Replaces the hard-coded `oncall` /
    `ext` / `wconsult` variable families: the solver creates a
    `oc_<key>[d, day]` indicator var for every (doctor, active-day)
    pair and applies per-type constraints (daily_required,
    next_day_off, frequency_cap, works_full_day, works_pm_only).
    """

    key: str
    label: str = ""
    start_hour: int = 20
    end_hour: int = 8
    days_active: frozenset[int] = field(default_factory=lambda: frozenset(range(7)))
    eligible_tiers: frozenset[str] = field(default_factory=frozenset)
    daily_required: int = 1
    post_shift_rest_hours: int = 11
    next_day_off: bool = True
    frequency_cap_days: int | None = 3
    counts_as_weekend_role: bool = False
    works_full_day: bool = False
    works_pm_only: bool = False
    legacy_role_alias: str | None = None


@dataclass
class Doctor:
    id: int
    tier: str
    eligible_stations: frozenset[str]
    # Per-doctor on-call eligibility, keyed by OnCallType.key. Empty means
    # the doctor is not eligible for any on-call type. Phase B: the only
    # enforced eligibility (advisory `OnCallType.eligible_tiers` is a UI
    # hint, mirroring Phase A's tier/station decoupling).
    eligible_oncall_types: frozenset[str] = field(default_factory=frozenset)
    # FTE = full-time equivalent, 0.0–1.0. 0.5 means the doctor is half-time
    # and should carry roughly half the workload of a full-timer.
    fte: float = 1.0
    # Hard cap on the number of on-call nights this doctor can take in the
    # horizon. None = no cap.
    max_oncalls: int | None = None


@dataclass
class Instance:
    n_days: int
    start_weekday: int
    doctors: list[Doctor]
    stations: list[Station]
    leave: dict[int, set[int]] = field(default_factory=dict)
    public_holidays: set[int] = field(default_factory=set)
    prev_oncall: set[int] = field(default_factory=set)
    # User-defined on-call shift types. Drives every on-call-related
    # solver variable family + constraint after Phase B.
    on_call_types: list[OnCallType] = field(default_factory=list)
    # Prior-period carry-in: weighted workload score each doctor brought into
    # this horizon. The solver adds this to its own weighted workload when
    # balancing fairness (higher = did more last period → gets less this one).
    prev_workload: dict[int, int] = field(default_factory=dict)
    # Per-doctor hard blocks that are NOT whole-day leave:
    # no_oncall — doctor can't take on-call on these days (can still do AM/PM).
    # no_session — doctor can't be assigned to a specific session on these days.
    no_oncall: dict[int, set[int]] = field(default_factory=dict)
    no_session: dict[int, dict[int, set[str]]] = field(default_factory=dict)
    # Soft positive preferences: doctor prefers a particular session on a day.
    # {doctor_id: {day_idx: {"AM", "PM"}}}. Rewarded via objective.
    prefer_session: dict[int, dict[int, set[str]]] = field(default_factory=dict)
    # Per-doctor role preferences: "Dr A wants ≥ N allocations of role X
    # this period". Role is either a station name (sums AM + PM hits on
    # that station), one of the legacy non-station roles
    # (ONCALL, WEEKEND_EXT, WEEKEND_CONSULT — back-compat), or any
    # user-defined OnCallType key. Stored as
    # {doctor_id: {role: (min_allocations, priority)}}. The solver emits
    # a soft shortfall penalty per unmet preference (see model.py S7).
    role_preferences: dict[int, dict[str, tuple[int, int]]] = field(
        default_factory=dict)
    # Manual overrides: force a specific assignment. Treated as hard constraints.
    # Each item is (doctor_id, day, station_name_or_None, session_or_None, role)
    # where role is one of "STATION" / "ONCALL_<type_key>" (post-Phase-B) or
    # the legacy three "ONCALL" / "EXT" / "WCONSULT" (mapped on parse).
    overrides: list[tuple[int, int, str | None, str | None, str]] = field(
        default_factory=list)

    def is_weekend(self, day: int) -> bool:
        wd = (self.start_weekday + day) % 7
        return wd >= 5 or day in self.public_holidays

    def weekday_of(self, day: int) -> int:
        return (self.start_weekday + day) % 7


DEFAULT_STATIONS: tuple[Station, ...] = (
    # Cross-sectional reading — consultant-led but senior-eligible too.
    Station("CT", ("AM", "PM"), 1, frozenset({"senior", "consultant"})),
    Station("MR", ("AM", "PM"), 1, frozenset({"senior", "consultant"})),
    # High-volume reading stations staffed by all tiers (2 doctors per session).
    Station("US", ("AM", "PM"), 2, frozenset({"junior", "senior", "consultant"})),
    Station("XR_REPORT", ("AM", "PM"), 2,
            frozenset({"junior", "senior", "consultant"}), is_reporting=True),
    # Interventional — consultant only.
    Station("IR", ("AM", "PM"), 1, frozenset({"consultant"})),
    Station("FLUORO", ("AM", "PM"), 1, frozenset({"consultant"})),
    # Ward / general reading — single-session cover, all tiers.
    Station("GEN_AM", ("AM",), 1, frozenset({"junior", "senior", "consultant"})),
    Station("GEN_PM", ("PM",), 1, frozenset({"junior", "senior", "consultant"})),
)

ALL_DAYS: frozenset[int] = frozenset(range(7))
WEEKEND_DAYS: frozenset[int] = frozenset({5, 6})


def default_on_call_types(
    *,
    weekday_oncall: bool = True,
    weekend_h8: bool = True,
    weekend_consultants_required: int = 1,
    h4_gap: int = 3,
    h5_post_call_off: bool = True,
    h6_senior_full_day: bool = True,
    h7_junior_pm: bool = True,
) -> list[OnCallType]:
    """Five-type on-call configuration that mirrors the legacy
    `oncall`/`ext`/`wconsult` variable families exactly.

    Used by both the v2→v3 migration (`scheduler.persistence.load_state`)
    and the synthetic generator below. Splitting night-call into a
    junior-only and senior-only type preserves the legacy
    "1 junior + 1 senior on-call per night" behaviour — a single
    `night_full` with `daily_required=2` would lose that.
    """
    types: list[OnCallType] = []
    night_days_idx: set[int] = set()
    if weekday_oncall:
        night_days_idx.update({0, 1, 2, 3, 4})
    if weekend_h8:
        night_days_idx.update({5, 6})
    night_days = frozenset(night_days_idx)
    weekend_days = WEEKEND_DAYS if weekend_h8 else frozenset()

    if night_days:
        types.append(OnCallType(
            key="oncall_jr",
            label="Night call (junior)",
            start_hour=20,
            end_hour=8,
            days_active=night_days,
            eligible_tiers=frozenset({"junior"}),
            daily_required=1,
            post_shift_rest_hours=11,
            next_day_off=h5_post_call_off,
            frequency_cap_days=h4_gap,
            counts_as_weekend_role=False,
            works_full_day=False,
            works_pm_only=h7_junior_pm,
            legacy_role_alias="ONCALL",
        ))
        types.append(OnCallType(
            key="oncall_sr",
            label="Night call (senior)",
            start_hour=20,
            end_hour=8,
            days_active=night_days,
            eligible_tiers=frozenset({"senior"}),
            daily_required=1,
            post_shift_rest_hours=11,
            next_day_off=h5_post_call_off,
            frequency_cap_days=h4_gap,
            counts_as_weekend_role=False,
            works_full_day=h6_senior_full_day,
            works_pm_only=False,
            legacy_role_alias="ONCALL",
        ))
    if weekend_days:
        types.append(OnCallType(
            key="weekend_ext_jr",
            label="Weekend extended (junior)",
            start_hour=8,
            end_hour=20,
            days_active=weekend_days,
            eligible_tiers=frozenset({"junior"}),
            daily_required=1,
            post_shift_rest_hours=0,
            next_day_off=False,
            frequency_cap_days=None,
            counts_as_weekend_role=True,
            legacy_role_alias="WEEKEND_EXT",
        ))
        types.append(OnCallType(
            key="weekend_ext_sr",
            label="Weekend extended (senior)",
            start_hour=8,
            end_hour=20,
            days_active=weekend_days,
            eligible_tiers=frozenset({"senior"}),
            daily_required=1,
            post_shift_rest_hours=0,
            next_day_off=False,
            frequency_cap_days=None,
            counts_as_weekend_role=True,
            legacy_role_alias="WEEKEND_EXT",
        ))
        if weekend_consultants_required > 0:
            types.append(OnCallType(
                key="weekend_consult",
                label="Weekend consultant",
                start_hour=8,
                end_hour=17,
                days_active=weekend_days,
                eligible_tiers=frozenset({"consultant"}),
                daily_required=int(weekend_consultants_required),
                post_shift_rest_hours=0,
                next_day_off=False,
                frequency_cap_days=None,
                counts_as_weekend_role=True,
                legacy_role_alias="WEEKEND_CONSULT",
            ))
    return types


def eligible_types_for_tier(
    tier: str, types: list[OnCallType]
) -> frozenset[str]:
    """Map a tier string to the set of OnCallType keys whose advisory
    `eligible_tiers` includes that tier. Used by `make_synthetic` and
    the v2→v3 migration to populate `Doctor.eligible_oncall_types`."""
    return frozenset(t.key for t in types if tier in t.eligible_tiers)


def _tier_split(n: int) -> tuple[int, int, int]:
    """Split total N doctors across (junior, senior, consultant).

    Rough mix reflecting the conversation: ~30–40 consultants, ~20 juniors,
    a handful of seniors. Minimum headcounts so every weekend role can be
    filled.
    """
    n_junior = max(4, int(round(n * 0.35)))
    n_senior = max(3, int(round(n * 0.15)))
    n_consult = max(6, n - n_junior - n_senior)
    # Re-balance if sum drifted.
    total = n_junior + n_senior + n_consult
    if total != n:
        n_consult += n - total
    return n_junior, n_senior, n_consult


def make_synthetic(
    n_doctors: int,
    n_days: int,
    *,
    seed: int = 0,
    start_weekday: int = 0,
    leave_rate: float = 0.03,
    stations: tuple[Station, ...] = DEFAULT_STATIONS,
) -> Instance:
    """Generate a synthetic instance.

    Parameters
    ----------
    n_doctors : total doctor count.
    n_days : horizon length.
    seed : RNG seed.
    start_weekday : 0=Mon..6=Sun for day 0.
    leave_rate : expected fraction of doctor-days that are on leave.
    """
    rng = random.Random(seed)
    n_j, n_s, n_c = _tier_split(n_doctors)

    # Synth defaults match the legacy `ConstraintConfig` shape:
    # weekday on-call OFF (weekday nights need explicit opt-in), H8
    # weekend coverage ON. Tests that need weekday on-call set the
    # synth's `inst.on_call_types` explicitly.
    on_call_types = default_on_call_types(weekday_oncall=False)
    elig_jr = eligible_types_for_tier("junior", on_call_types)
    elig_sr = eligible_types_for_tier("senior", on_call_types)
    elig_co = eligible_types_for_tier("consultant", on_call_types)

    doctors: list[Doctor] = []
    did = 0
    for _ in range(n_j):
        doctors.append(Doctor(did, "junior",
                              _eligible_for_tier("junior", stations, rng),
                              eligible_oncall_types=elig_jr))
        did += 1
    for _ in range(n_s):
        doctors.append(Doctor(did, "senior",
                              _eligible_for_tier("senior", stations, rng),
                              eligible_oncall_types=elig_sr))
        did += 1
    for _ in range(n_c):
        doctors.append(Doctor(did, "consultant",
                              _eligible_for_tier("consultant", stations, rng),
                              eligible_oncall_types=elig_co))
        did += 1

    leave: dict[int, set[int]] = {}
    for d in doctors:
        days_off = {day for day in range(n_days) if rng.random() < leave_rate}
        if days_off:
            leave[d.id] = days_off

    return Instance(
        n_days=n_days,
        start_weekday=start_weekday,
        doctors=doctors,
        stations=list(stations),
        leave=leave,
        on_call_types=on_call_types,
    )


def _eligible_for_tier(
    tier: str, stations: tuple[Station, ...], rng: random.Random
) -> frozenset[str]:
    """Pick an eligibility subset for this doctor.

    Every doctor is eligible for their tier-allowed stations. We then drop a
    small random subset (≤ 1 station) to add realistic eligibility variation
    without making instances infeasible.
    """
    allowed = [s.name for s in stations if tier in s.eligible_tiers]
    if len(allowed) > 4 and rng.random() < 0.3:
        drop = rng.choice(allowed)
        allowed = [s for s in allowed if s != drop]
    return frozenset(allowed)
