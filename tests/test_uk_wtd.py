"""UK NHS WTD compliance checker — hand-computed fixtures for each rule.

Rules covered (per `docs/INDUSTRY_CONTEXT.md §5`):

  W1  avg weekly hours ≤ 48 over horizon
  W2  ≤ 72h in any rolling 7 calendar days
  W3  ≤ 13h per shift
  W4  ≥ 11h rest between consecutive shifts
  W5  ≤ 4 consecutive long-day dates
  W6  ≤ 7 consecutive nights (on-call)

Each test builds the minimum AssignmentRow fixture that exercises exactly
one rule so a regression in a single check doesn't silently fall out of
a blanket "ran six rules" assertion.
"""

from __future__ import annotations

from datetime import date, timedelta

from api.compliance.uk_wtd import WtdConfig, check_uk_wtd
from api.models.events import AssignmentRow
from api.models.session import Horizon, Hours, SessionState


def _state(*, n_days: int = 28, weekday_am_pm_hours: float = 4.0,
           oncall_weekday_hours: float = 12.0,
           ext_hours: float = 12.0) -> SessionState:
    return SessionState(
        horizon=Horizon(start_date=date(2026, 1, 5), n_days=n_days),  # Mon
        hours=Hours(
            weekday_am=weekday_am_pm_hours,
            weekday_pm=weekday_am_pm_hours,
            weekend_am=weekday_am_pm_hours,
            weekend_pm=weekday_am_pm_hours,
            weekday_oncall=oncall_weekday_hours,
            weekend_oncall=16.0,
            weekend_ext=ext_hours,
            weekend_consult=8.0,
        ),
    )


def _row(doctor: str, iso: str, role: str) -> AssignmentRow:
    return AssignmentRow(doctor=doctor, date=date.fromisoformat(iso), role=role)


# --------------------------------------------------------------- W1 avg


def test_w1_average_weekly_ok() -> None:
    """10 working days × 4h = 40h over 2 weeks = 20h/week avg — fine."""
    state = _state()
    rows = [
        _row("alice", f"2026-01-{d:02d}", "STATION_GEN_AM")
        for d in range(5, 15) if date(2026, 1, d).weekday() < 5
    ]
    v = check_uk_wtd(state, rows)
    w1 = [x for x in v if x.rule == "W1_AVG_WEEKLY_HOURS"]
    assert w1 == []


def test_w1_average_weekly_breach() -> None:
    """Cap the avg-weekly at 10h so it's easy to breach.
    10 × 4h = 40h over 10-day span (~1.4 weeks) ≈ 28h/week > 10h → breach."""
    state = _state()
    rows = [
        _row("alice", f"2026-01-{d:02d}", "STATION_GEN_AM")
        for d in range(5, 15) if date(2026, 1, d).weekday() < 5
    ]
    v = check_uk_wtd(state, rows, config=WtdConfig(max_avg_weekly_hours=10.0))
    assert any(x.rule == "W1_AVG_WEEKLY_HOURS" for x in v)


# --------------------------------------------------------------- W2 rolling 7


def test_w2_rolling_7_day_breach() -> None:
    """14h/day × 7 days = 98h > 72h. Use oncall + AM/PM same day? Those
    can't coexist per H6/H7, so use 2x4h station + 1x12h ext on weekend
    days (12h+8h+8h = 28h) — no, use oncall roles alone. Simpler: force
    big per-day hours via a custom Hours config. Give a 30h weekday
    "session" so 3 consecutive days tops the 72h cap."""
    state = _state(weekday_am_pm_hours=14.0)  # AM=14h, PM=14h → 28h/day (above 13h cap)
    # Keep shift length valid by running only one big AM or PM per day.
    rows = [_row("alice", f"2026-01-{d:02d}", "STATION_GEN_AM") for d in range(5, 12)]
    v = check_uk_wtd(state, rows, config=WtdConfig(max_shift_hours=100))
    # 14h × 7 = 98h in first 7-day window.
    assert any(x.rule == "W2_ROLLING_7_DAYS" for x in v)


def test_w2_rolling_7_day_ok() -> None:
    state = _state()
    rows = [_row("alice", f"2026-01-{d:02d}", "STATION_GEN_AM") for d in range(5, 8)]
    v = check_uk_wtd(state, rows)
    assert not any(x.rule == "W2_ROLLING_7_DAYS" for x in v)


# --------------------------------------------------------------- W3 shift length


def test_w3_oncall_exceeding_13h() -> None:
    """Default weekday oncall is 12h — under cap. Bump to 14h to force
    a W3 breach on a single shift."""
    state = _state(oncall_weekday_hours=14.0)
    rows = [_row("alice", "2026-01-05", "ONCALL")]
    v = check_uk_wtd(state, rows)
    assert any(x.rule == "W3_MAX_SHIFT_HOURS" for x in v)


def test_w3_weekend_oncall_16h_breach() -> None:
    """Default weekend oncall = 16h — above the 13h cap → default breach."""
    state = _state()
    # 2026-01-10 is Saturday
    rows = [_row("alice", "2026-01-10", "ONCALL")]
    v = check_uk_wtd(state, rows)
    assert any(x.rule == "W3_MAX_SHIFT_HOURS" for x in v)


# --------------------------------------------------------------- W4 rest


def test_w4_am_pm_same_day_is_one_shift() -> None:
    """AM (08:00–12:00) + PM (13:00–17:00) on same day collapses into a
    single shift — 1h lunch is NOT treated as end-of-shift. Without the
    merge step, the gap check would flag 1h < 11h."""
    state = _state()
    rows = [
        _row("alice", "2026-01-05", "STATION_GEN_AM"),
        _row("alice", "2026-01-05", "STATION_GEN_PM"),
    ]
    v = check_uk_wtd(state, rows)
    assert not any(x.rule == "W4_MIN_REST_BETWEEN" for x in v)


def test_w4_pm_then_next_day_am_has_adequate_rest() -> None:
    """PM ends 17:00 Mon → AM starts 08:00 Tue = 15h rest. OK."""
    state = _state()
    rows = [
        _row("alice", "2026-01-05", "STATION_GEN_PM"),
        _row("alice", "2026-01-06", "STATION_GEN_AM"),
    ]
    v = check_uk_wtd(state, rows)
    assert not any(x.rule == "W4_MIN_REST_BETWEEN" for x in v)


def test_w4_junior_pm_then_oncall_same_night_breaches() -> None:
    """PM 13:00–17:00 on Mon, ONCALL 20:00 Mon → 3h gap. Breach.
    Surfaces the H7 vs WTD tension the paper should flag."""
    state = _state()
    rows = [
        _row("alice", "2026-01-05", "STATION_GEN_PM"),
        _row("alice", "2026-01-05", "ONCALL"),
    ]
    v = check_uk_wtd(state, rows)
    assert any(x.rule == "W4_MIN_REST_BETWEEN" for x in v)


# --------------------------------------------------------------- W5 long days


def test_w5_four_consecutive_long_days_ok() -> None:
    """4 × long day is the cap itself. 5+ is a breach."""
    state = _state(weekday_am_pm_hours=6.0)  # AM+PM merged = 12h (≥10h = long)
    rows = []
    for d in range(5, 9):  # Mon–Thu → 4 consecutive long days
        rows.append(_row("alice", f"2026-01-{d:02d}", "STATION_GEN_AM"))
        rows.append(_row("alice", f"2026-01-{d:02d}", "STATION_GEN_PM"))
    # AM ends 12:00, PM starts 13:00 — merged to one 12h shift.
    v = check_uk_wtd(state, rows, config=WtdConfig(max_shift_hours=100))
    assert not any(x.rule == "W5_CONSECUTIVE_LONG_DAYS" for x in v)


def test_w5_five_consecutive_long_days_breach() -> None:
    state = _state(weekday_am_pm_hours=6.0)
    rows = []
    for d in range(5, 10):
        rows.append(_row("alice", f"2026-01-{d:02d}", "STATION_GEN_AM"))
        rows.append(_row("alice", f"2026-01-{d:02d}", "STATION_GEN_PM"))
    v = check_uk_wtd(state, rows, config=WtdConfig(max_shift_hours=100))
    assert any(x.rule == "W5_CONSECUTIVE_LONG_DAYS" for x in v)


# --------------------------------------------------------------- W6 nights


def test_w6_eight_consecutive_nights_breach() -> None:
    state = _state(n_days=30)
    rows = [_row("alice", f"2026-01-{d:02d}", "ONCALL") for d in range(5, 13)]
    v = check_uk_wtd(state, rows, config=WtdConfig(max_shift_hours=100,
                                                   min_rest_between_hours=0.0))
    assert any(x.rule == "W6_CONSECUTIVE_NIGHTS" for x in v)


def test_w6_seven_consecutive_nights_ok() -> None:
    state = _state(n_days=30)
    rows = [_row("alice", f"2026-01-{d:02d}", "ONCALL") for d in range(5, 12)]
    v = check_uk_wtd(state, rows, config=WtdConfig(max_shift_hours=100,
                                                   min_rest_between_hours=0.0))
    assert not any(x.rule == "W6_CONSECUTIVE_NIGHTS" for x in v)


# --------------------------------------------------------------- multi-doctor


def test_violations_are_scoped_per_doctor() -> None:
    """Alice breaches; Bob doesn't. Only Alice should be flagged."""
    state = _state()
    rows = [
        _row("alice", "2026-01-10", "ONCALL"),  # 16h weekend oncall breaches W3
        _row("bob",   "2026-01-05", "STATION_GEN_AM"),  # 4h, no breaches
    ]
    v = check_uk_wtd(state, rows)
    docs = {x.doctor for x in v}
    assert docs == {"alice"}


def test_empty_assignments_returns_no_violations() -> None:
    state = _state()
    assert check_uk_wtd(state, []) == []


# --------------------------------------------------------------- endpoint


def test_uk_wtd_endpoint_happy_path(client) -> None:
    """Post a small roster, default config, get a structured report."""
    client.post("/api/state/scenarios/radiology_small")
    body = {
        "assignments": [
            {"doctor": "D01", "date": "2026-01-05", "role": "STATION_GEN_AM"},
            {"doctor": "D01", "date": "2026-01-05", "role": "STATION_GEN_PM"},
            {"doctor": "D01", "date": "2026-01-10", "role": "ONCALL"},
        ],
    }
    r = client.post("/api/compliance/uk_wtd", json=body)
    assert r.status_code == 200, r.text
    payload = r.json()
    assert "ok" in payload
    assert "violation_count" in payload
    assert "by_rule" in payload
    # 16h weekend oncall breaches the default 13h W3 cap.
    assert payload["error_count"] >= 1
    assert payload["ok"] is False


def test_uk_wtd_endpoint_accepts_config_patch(client) -> None:
    """Relax every threshold the single-shift fixture touches; confirm
    the patch flows through into the response's echoed config block."""
    client.post("/api/state/scenarios/radiology_small")
    body = {
        "assignments": [
            {"doctor": "D01", "date": "2026-01-10", "role": "ONCALL"},
        ],
        "config": {
            "max_shift_hours": 20.0,
            "max_avg_weekly_hours": 200.0,
            "max_hours_per_7_days": 200.0,
        },
    }
    r = client.post("/api/compliance/uk_wtd", json=body)
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["ok"] is True
    assert payload["violation_count"] == 0
    assert payload["config"]["max_shift_hours"] == 20.0
    assert payload["config"]["max_avg_weekly_hours"] == 200.0
