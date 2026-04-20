"""Problem-instance data classes and a synthetic generator.

The synthetic generator produces realistic-shaped instances for benchmarking
without needing real hospital data. Tier mix, station list, and leave rates
match the defaults documented in `docs/CONSTRAINTS.md §5`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

TIERS = ("junior", "senior", "consultant")
SUBSPECS = ("A", "B", "C")
SESSIONS = ("AM", "PM")


@dataclass(frozen=True)
class Station:
    name: str
    sessions: tuple[str, ...]
    required_per_session: int
    eligible_tiers: frozenset[str]
    is_reporting: bool = False


@dataclass
class Doctor:
    id: int
    tier: str
    subspec: str | None
    eligible_stations: frozenset[str]


@dataclass
class Instance:
    n_days: int
    start_weekday: int
    doctors: list[Doctor]
    stations: list[Station]
    leave: dict[int, set[int]] = field(default_factory=dict)
    public_holidays: set[int] = field(default_factory=set)
    prev_oncall: set[int] = field(default_factory=set)
    weekend_am_pm_enabled: bool = False
    # Prior-period carry-in: weighted workload score each doctor brought into
    # this horizon. The solver adds this to its own weighted workload when
    # balancing fairness (higher = did more last period → gets less this one).
    prev_workload: dict[int, int] = field(default_factory=dict)

    def is_weekend(self, day: int) -> bool:
        wd = (self.start_weekday + day) % 7
        return wd >= 5 or day in self.public_holidays

    def weekday_of(self, day: int) -> int:
        return (self.start_weekday + day) % 7


DEFAULT_STATIONS: tuple[Station, ...] = (
    Station("CT", ("AM", "PM"), 1, frozenset({"consultant"})),
    Station("MR", ("AM", "PM"), 1, frozenset({"consultant"})),
    Station("US", ("AM", "PM"), 1, frozenset({"junior", "senior", "consultant"})),
    Station("XR_REPORT", ("AM", "PM"), 1,
            frozenset({"junior", "senior", "consultant"}), is_reporting=True),
    Station("IR", ("AM", "PM"), 1, frozenset({"consultant"})),
    Station("FLUORO", ("AM", "PM"), 1, frozenset({"consultant"})),
    Station("GEN_AM", ("AM",), 1, frozenset({"junior", "senior", "consultant"})),
    Station("GEN_PM", ("PM",), 1, frozenset({"junior", "senior", "consultant"})),
)


def _tier_split(n: int) -> tuple[int, int, int]:
    """Split total N doctors across (junior, senior, consultant).

    Rough mix reflecting the conversation: ~30–40 consultants, ~20 juniors,
    a handful of seniors. Minimum headcounts so every weekend role can be
    filled.
    """
    n_junior = max(4, int(round(n * 0.35)))
    n_senior = max(3, int(round(n * 0.15)))
    n_consult = max(6, n - n_junior - n_senior)
    # Ensure at least 2 consultants per subspec.
    n_consult = max(n_consult, 2 * len(SUBSPECS))
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

    doctors: list[Doctor] = []
    did = 0
    for _ in range(n_j):
        doctors.append(Doctor(did, "junior", None,
                              _eligible_for_tier("junior", stations, rng)))
        did += 1
    for _ in range(n_s):
        doctors.append(Doctor(did, "senior", None,
                              _eligible_for_tier("senior", stations, rng)))
        did += 1
    for i in range(n_c):
        subspec = SUBSPECS[i % len(SUBSPECS)]
        doctors.append(Doctor(did, "consultant", subspec,
                              _eligible_for_tier("consultant", stations, rng)))
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
