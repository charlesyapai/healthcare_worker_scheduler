"""UK junior-doctor 2016 contract + EU Working Time Directive conformance.

Six rules encoded here map onto `docs/INDUSTRY_CONTEXT.md §5`:

  W1  ≤ 48 h averaged over the reference period (default 26 weeks; we
      average across the roster horizon when shorter).
  W2  ≤ 72 h in any rolling 7 calendar days.
  W3  ≤ 13 h per shift.
  W4  ≥ 11 h rest between consecutive shifts.
  W5  ≤ 4 consecutive "long day" dates (default threshold: shift ≥ 10 h).
  W6  ≤ 7 consecutive nights (nights = on-call shifts in our model).

The checker consumes a `SessionState` + a list of assignment rows and
returns one `WtdViolation` per breach. No CP-SAT or solver dependency —
the module is a pure post-solve audit.

Shift clock times are approximated from the `HoursConfig` durations
and conventional start times (AM=08:00, PM=13:00, on-call=20:00,
weekend-ext/consult=08:00). Exact clinical shift times vary by Trust;
the approximation is calibrated to catch the qualitative breaches the
WTD rule-set targets (not-enough-rest, too-many-nights-in-a-row).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date, datetime, time, timedelta
from typing import Iterable

from api.models.events import AssignmentRow
from api.models.session import SessionState


# --------------------------------------------------------------- config


@dataclass(frozen=True)
class WtdConfig:
    """Rule thresholds. Defaults follow the UK junior-doctor 2016 contract
    + EU WTD 2003/88/EC. Adjustable for research ablations (e.g. test
    what happens if the 48-hr cap is lifted)."""

    max_avg_weekly_hours: float = 48.0
    max_hours_per_7_days: float = 72.0
    max_shift_hours: float = 13.0
    min_rest_between_hours: float = 11.0
    max_consecutive_long_days: int = 4
    max_consecutive_nights: int = 7
    long_day_threshold_hours: float = 10.0
    # Weekly-average reference period (weeks). When the roster horizon is
    # shorter than this we scale the check to horizon length so we don't
    # accuse a 2-week roster of violating a 26-week average.
    reference_period_weeks: int = 26


@dataclass
class WtdViolation:
    """One breach of one rule for one doctor.

    `severity` = "error" for statutory rules (W1–W4) that reviewers must
    defend against; "warning" for W5/W6 because the UK contract
    sometimes tolerates exception reports (see INDUSTRY_CONTEXT.md §5).
    """

    rule: str          # "W1_AVG_WEEKLY" / "W2_ROLLING_7" / ...
    severity: str      # "error" | "warning"
    doctor: str
    message: str
    detail: dict = field(default_factory=dict)


# --------------------------------------------------------------- shifts


@dataclass(frozen=True)
class _ShiftPeriod:
    """Internal — one shift for one doctor with wall-clock times."""

    doctor: str
    start: datetime
    end: datetime
    hours: float
    kind: str          # "am" | "pm" | "oncall" | "ext" | "wconsult"


_AM_START = time(8, 0)
_PM_START = time(13, 0)
_ONCALL_START = time(20, 0)
_EXT_START = time(8, 0)
_WCONSULT_START = time(8, 0)


def _is_weekend(d: _date, holidays: set[_date]) -> bool:
    return d.weekday() >= 5 or d in holidays


def _role_to_shift(
    row: AssignmentRow,
    state: SessionState,
    holidays: set[_date],
) -> _ShiftPeriod | None:
    """Translate one assignment row into a shift period. Unknown roles
    are skipped rather than flagged — the validator is the authority on
    role shape."""
    hrs = state.hours
    d = row.date
    we = _is_weekend(d, holidays)
    role = row.role
    if role.startswith("STATION_"):
        if role.endswith("_AM"):
            h = hrs.weekend_am if we else hrs.weekday_am
            start = datetime.combine(d, _AM_START)
            kind = "am"
        elif role.endswith("_PM"):
            h = hrs.weekend_pm if we else hrs.weekday_pm
            start = datetime.combine(d, _PM_START)
            kind = "pm"
        else:
            return None
    elif role == "ONCALL":
        h = hrs.weekend_oncall if we else hrs.weekday_oncall
        start = datetime.combine(d, _ONCALL_START)
        kind = "oncall"
    elif role == "WEEKEND_EXT":
        h = hrs.weekend_ext
        start = datetime.combine(d, _EXT_START)
        kind = "ext"
    elif role == "WEEKEND_CONSULT":
        h = hrs.weekend_consult
        start = datetime.combine(d, _WCONSULT_START)
        kind = "wconsult"
    else:
        return None
    return _ShiftPeriod(
        doctor=row.doctor,
        start=start,
        end=start + timedelta(hours=h),
        hours=float(h),
        kind=kind,
    )


def _merge_same_day_am_pm(shifts: list[_ShiftPeriod]) -> list[_ShiftPeriod]:
    """Collapse a doctor's AM + PM on the same date into one contiguous
    shift. Without this, W4 would flag AM→PM as "only 1 hour rest"; in
    clinical practice AM+PM is one working day, not two separate shifts.

    The merged shift keeps the AM start and the PM end; its hours are
    the literal sum (not end-minus-start, so a 1-hour lunch gap doesn't
    count toward hours worked).
    """
    by_day: dict[tuple[str, _date], list[_ShiftPeriod]] = {}
    for s in shifts:
        by_day.setdefault((s.doctor, s.start.date()), []).append(s)
    merged: list[_ShiftPeriod] = []
    for (_doc, _d), group in by_day.items():
        am = next((s for s in group if s.kind == "am"), None)
        pm = next((s for s in group if s.kind == "pm"), None)
        others = [s for s in group if s.kind not in ("am", "pm")]
        if am and pm:
            merged.append(_ShiftPeriod(
                doctor=am.doctor,
                start=am.start,
                end=pm.end,
                hours=am.hours + pm.hours,
                kind="day",
            ))
        else:
            merged.extend(s for s in (am, pm) if s is not None)
        merged.extend(others)
    merged.sort(key=lambda s: (s.doctor, s.start))
    return merged


def _build_shifts(
    state: SessionState, assignments: Iterable[AssignmentRow],
) -> dict[str, list[_ShiftPeriod]]:
    holidays = set(state.horizon.public_holidays)
    raw: list[_ShiftPeriod] = []
    for row in assignments:
        sp = _role_to_shift(row, state, holidays)
        if sp is not None:
            raw.append(sp)
    merged = _merge_same_day_am_pm(raw)
    by_doc: dict[str, list[_ShiftPeriod]] = {}
    for s in merged:
        by_doc.setdefault(s.doctor, []).append(s)
    return by_doc


# --------------------------------------------------------------- rules


def _check_shift_length(
    shifts: list[_ShiftPeriod], cfg: WtdConfig,
) -> list[WtdViolation]:
    out: list[WtdViolation] = []
    for s in shifts:
        if s.hours > cfg.max_shift_hours + 1e-9:
            out.append(WtdViolation(
                rule="W3_MAX_SHIFT_HOURS",
                severity="error",
                doctor=s.doctor,
                message=(
                    f"Shift on {s.start.date().isoformat()} lasts "
                    f"{s.hours:.1f}h (> {cfg.max_shift_hours}h cap)."
                ),
                detail={
                    "date": s.start.date().isoformat(),
                    "hours": round(s.hours, 2),
                    "kind": s.kind,
                },
            ))
    return out


def _check_rest_between(
    shifts: list[_ShiftPeriod], cfg: WtdConfig,
) -> list[WtdViolation]:
    out: list[WtdViolation] = []
    for i in range(len(shifts) - 1):
        gap_h = (shifts[i + 1].start - shifts[i].end).total_seconds() / 3600
        if gap_h < cfg.min_rest_between_hours - 1e-9:
            out.append(WtdViolation(
                rule="W4_MIN_REST_BETWEEN",
                severity="error",
                doctor=shifts[i].doctor,
                message=(
                    f"Only {gap_h:.1f}h rest between shift ending "
                    f"{shifts[i].end.isoformat(sep=' ')} and shift "
                    f"starting {shifts[i + 1].start.isoformat(sep=' ')} "
                    f"(< {cfg.min_rest_between_hours}h minimum)."
                ),
                detail={
                    "gap_hours": round(gap_h, 2),
                    "prev_end": shifts[i].end.isoformat(),
                    "next_start": shifts[i + 1].start.isoformat(),
                    "prev_kind": shifts[i].kind,
                    "next_kind": shifts[i + 1].kind,
                },
            ))
    return out


def _daily_hours(shifts: list[_ShiftPeriod]) -> dict[_date, float]:
    """Attribute each shift's hours to its start-date. Oncall hours that
    cross midnight are counted toward the start date — simpler to
    reason about and the rolling-7-day window still captures them.
    """
    out: dict[_date, float] = {}
    for s in shifts:
        d = s.start.date()
        out[d] = out.get(d, 0.0) + s.hours
    return out


def _check_rolling_7(
    shifts: list[_ShiftPeriod], cfg: WtdConfig,
) -> list[WtdViolation]:
    """W2 — no rolling 7-day window can exceed 72h. Walks every start-
    date of a worked day and sums the next 7 days inclusive."""
    out: list[WtdViolation] = []
    if not shifts:
        return out
    daily = _daily_hours(shifts)
    days = sorted(daily.keys())
    for anchor in days:
        total = 0.0
        for offset in range(7):
            d = anchor + timedelta(days=offset)
            total += daily.get(d, 0.0)
        if total > cfg.max_hours_per_7_days + 1e-9:
            out.append(WtdViolation(
                rule="W2_ROLLING_7_DAYS",
                severity="error",
                doctor=shifts[0].doctor,
                message=(
                    f"{total:.1f}h worked in the 7-day window starting "
                    f"{anchor.isoformat()} "
                    f"(> {cfg.max_hours_per_7_days}h cap)."
                ),
                detail={
                    "window_start": anchor.isoformat(),
                    "hours": round(total, 2),
                },
            ))
            # Only report the first breaching window to avoid N duplicate
            # alerts for one overloaded stretch.
            break
    return out


def _check_average_weekly(
    shifts: list[_ShiftPeriod], cfg: WtdConfig,
) -> list[WtdViolation]:
    """W1 — average weekly hours over the horizon. When the horizon is
    shorter than the statutory reference period (26 weeks default), we
    still apply the 48-hour cap to the horizon average; that's the
    spirit of the rule for a short roster."""
    if not shifts:
        return []
    daily = _daily_hours(shifts)
    if not daily:
        return []
    total_hours = sum(daily.values())
    first_day = min(daily.keys())
    last_day = max(daily.keys())
    horizon_days = (last_day - first_day).days + 1
    weeks = max(horizon_days / 7.0, 1.0 / 7.0)
    avg = total_hours / weeks
    if avg > cfg.max_avg_weekly_hours + 1e-9:
        return [WtdViolation(
            rule="W1_AVG_WEEKLY_HOURS",
            severity="error",
            doctor=shifts[0].doctor,
            message=(
                f"Average {avg:.1f}h/week over "
                f"{horizon_days} days ({weeks:.1f} weeks) "
                f"(> {cfg.max_avg_weekly_hours}h cap)."
            ),
            detail={
                "total_hours": round(total_hours, 2),
                "weeks": round(weeks, 2),
                "average_weekly_hours": round(avg, 2),
            },
        )]
    return []


def _longest_consecutive_run(sorted_dates: list[_date]) -> tuple[int, list[_date]]:
    """Helper: longest run of consecutive calendar days in a sorted list."""
    if not sorted_dates:
        return 0, []
    best = cur = 1
    best_end = cur_start = sorted_dates[0]
    best_start = sorted_dates[0]
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
            cur += 1
        else:
            cur = 1
            cur_start = sorted_dates[i]
        if cur > best:
            best = cur
            best_end = sorted_dates[i]
            best_start = cur_start
    return best, [best_start, best_end]


def _check_consecutive_long_days(
    shifts: list[_ShiftPeriod], cfg: WtdConfig,
) -> list[WtdViolation]:
    long_dates = sorted({
        s.start.date() for s in shifts
        if s.hours >= cfg.long_day_threshold_hours - 1e-9
    })
    best, span = _longest_consecutive_run(long_dates)
    if best > cfg.max_consecutive_long_days:
        return [WtdViolation(
            rule="W5_CONSECUTIVE_LONG_DAYS",
            severity="warning",
            doctor=shifts[0].doctor if shifts else "",
            message=(
                f"{best} consecutive long days ({span[0].isoformat()} → "
                f"{span[1].isoformat()}) — statutory soft cap is "
                f"{cfg.max_consecutive_long_days}."
            ),
            detail={
                "run_length": best,
                "start": span[0].isoformat(),
                "end": span[1].isoformat(),
                "threshold_hours": cfg.long_day_threshold_hours,
            },
        )]
    return []


def _check_consecutive_nights(
    shifts: list[_ShiftPeriod], cfg: WtdConfig,
) -> list[WtdViolation]:
    night_dates = sorted({s.start.date() for s in shifts if s.kind == "oncall"})
    best, span = _longest_consecutive_run(night_dates)
    if best > cfg.max_consecutive_nights:
        return [WtdViolation(
            rule="W6_CONSECUTIVE_NIGHTS",
            severity="warning",
            doctor=shifts[0].doctor if shifts else "",
            message=(
                f"{best} consecutive nights on-call "
                f"({span[0].isoformat()} → {span[1].isoformat()}) — "
                f"statutory soft cap is {cfg.max_consecutive_nights}."
            ),
            detail={
                "run_length": best,
                "start": span[0].isoformat(),
                "end": span[1].isoformat(),
            },
        )]
    return []


# --------------------------------------------------------------- public


def check_uk_wtd(
    state: SessionState,
    assignments: Iterable[AssignmentRow],
    *,
    config: WtdConfig | None = None,
) -> list[WtdViolation]:
    """Run all six UK WTD checks against `assignments`. Returns the full
    list of breaches (may be empty). Per-doctor ordering is preserved;
    inside one doctor's block, rules are emitted W1 → W6."""
    cfg = config or WtdConfig()
    shifts_by_doc = _build_shifts(state, assignments)
    out: list[WtdViolation] = []
    for doctor, shifts in sorted(shifts_by_doc.items()):
        # _build_shifts already sorts within a doctor by start time.
        out.extend(_check_average_weekly(shifts, cfg))
        out.extend(_check_rolling_7(shifts, cfg))
        out.extend(_check_shift_length(shifts, cfg))
        out.extend(_check_rest_between(shifts, cfg))
        out.extend(_check_consecutive_long_days(shifts, cfg))
        out.extend(_check_consecutive_nights(shifts, cfg))
    return out
