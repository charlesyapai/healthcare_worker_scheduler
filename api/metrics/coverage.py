"""Coverage metrics — required-vs-actual + shortfall + over-coverage.

Per `docs/RESEARCH_METRICS.md §5` and `docs/INDUSTRY_CONTEXT.md §3`.
These are first-class metrics in the NRP literature and the primary
signal for comparing optimisation methods against heuristic baselines
(a heuristic that leaves slots empty scores a high shortfall; a solver
that over-staffs scores high over-coverage).

Hard-constraint H1 is zero-tolerance in the CP-SAT model — every
feasible solve satisfies shortfall = over = 0 by construction. Useful
signals come from the greedy / random-repair baselines, which do not
guarantee either.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from api.models.events import AssignmentRow
from api.models.session import SessionState


def _is_weekend(d: date, holidays: set[date]) -> bool:
    return d.weekday() >= 5 or d in holidays


def compute_coverage(
    state: SessionState,
    assignments: list[AssignmentRow],
) -> dict[str, Any]:
    """Return coverage metrics over a caller-provided roster.

    Output shape (JSON-serialisable):
      - shortfall_total: sum over slots of max(0, required - assigned)
      - over_total: sum over slots of max(0, assigned - required)
      - ok: shortfall_total == 0 and over_total == 0
      - station_gaps: top-N (date, station, session) with the biggest
        shortfall. Useful for drilling into where a heuristic breaks down.
      - per_station: {station_name: {required, assigned, shortfall, over}}
    """
    horizon = state.horizon
    if not horizon.start_date or horizon.n_days <= 0:
        return {
            "shortfall_total": 0, "over_total": 0, "ok": True,
            "station_gaps": [], "per_station": {},
        }

    start = horizon.start_date
    dates = [start + timedelta(days=i) for i in range(horizon.n_days)]
    holidays = set(horizon.public_holidays or [])

    # Required per (date, station, session). Per-station weekday/weekend
    # gates control whether the slot is in scope on a given day.
    required: dict[tuple[date, str, str], int] = {}
    for d in dates:
        we = _is_weekend(d, holidays)
        for st in state.stations:
            if we and not st.weekend_enabled:
                continue
            if not we and not st.weekday_enabled:
                continue
            for sess in st.sessions:
                required[(d, st.name, sess)] = st.required_per_session

    # Actual per (date, station, session).
    actual: dict[tuple[date, str, str], int] = defaultdict(int)
    for a in assignments:
        r = a.role.upper()
        if not r.startswith("STATION_"):
            continue
        inner = r[len("STATION_"):]
        parts = inner.rsplit("_", 1)
        if len(parts) != 2 or parts[1] not in ("AM", "PM"):
            continue
        station, sess = parts
        actual[(a.date, station, sess)] += 1

    shortfall_total = 0
    over_total = 0
    gaps: list[dict] = []
    per_station: dict[str, dict[str, int]] = defaultdict(
        lambda: {"required": 0, "assigned": 0, "shortfall": 0, "over": 0}
    )
    all_keys = set(required.keys()) | set(actual.keys())
    for key in all_keys:
        req = required.get(key, 0)
        got = actual.get(key, 0)
        short = max(0, req - got)
        over = max(0, got - req)
        shortfall_total += short
        over_total += over
        d, st, sess = key
        ps = per_station[st]
        ps["required"] += req
        ps["assigned"] += got
        ps["shortfall"] += short
        ps["over"] += over
        if short > 0 or over > 0:
            gaps.append({
                "date": d.isoformat(),
                "station": st,
                "session": sess,
                "required": req,
                "assigned": got,
                "shortfall": short,
                "over": over,
            })
    gaps.sort(key=lambda g: (-g["shortfall"], -g["over"], g["date"]))
    return {
        "shortfall_total": shortfall_total,
        "over_total": over_total,
        "ok": shortfall_total == 0 and over_total == 0,
        "station_gaps": gaps[:20],
        "per_station": dict(per_station),
    }
