"""Stress tests: vary constraints and verify the model produces valid rosters.

Scenarios:
  A  — Baseline                          (reference)
  B  — Heavy leave (15%)
  C  — Public holidays mid-month
  D  — Month starts on a Saturday
  E  — Higher station headcount (2 per slot)
  F  — Prev-oncall seed (continuity)
  G  — Tight tier mix (minimum viable N)
  H  — Custom station list (no FLUORO, add 2 reporting stations)
  I  — Very short horizon (3 days, no weekend)
  J  — Long horizon (42 days)

For each, we solve and then verify every hard constraint on the returned
assignment. A single-line pass/fail per scenario is printed. Any
verification failure is a bug in the model.
"""

from __future__ import annotations

import time
from dataclasses import replace

from scheduler.instance import DEFAULT_STATIONS, Doctor, Instance, Station, make_synthetic
from scheduler.model import solve


def verify(inst: Instance, result) -> list[str]:
    """Return a list of violations. Empty list = roster is valid."""
    violations: list[str] = []
    if result.status not in ("OPTIMAL", "FEASIBLE"):
        return [f"solver status={result.status}"]

    st_assigns = result.assignments["stations"]
    oncall = result.assignments["oncall"]
    ext = result.assignments["ext"]
    wconsult = result.assignments["wconsult"]
    doc_by_id = {d.id: d for d in inst.doctors}
    station_by_name = {s.name: s for s in inst.stations}

    # H1 — station coverage.
    from collections import Counter
    cov: Counter = Counter()
    for (did, day, sname, sess) in st_assigns:
        cov[(day, sname, sess)] += 1
    for day in range(inst.n_days):
        if inst.is_weekend(day) and not inst.weekend_am_pm_enabled:
            continue
        for st in inst.stations:
            for sess in st.sessions:
                got = cov.get((day, st.name, sess), 0)
                if got != st.required_per_session:
                    violations.append(f"H1 day={day} {st.name}/{sess}: {got}/{st.required_per_session}")

    # H2 — one slot per session per doctor.
    per_sess: Counter = Counter()
    for (did, day, sname, sess) in st_assigns:
        per_sess[(did, day, sess)] += 1
    for k, v in per_sess.items():
        if v > 1:
            violations.append(f"H2 doctor={k[0]} day={k[1]} sess={k[2]}: {v}")

    # H3 — station eligibility.
    for (did, day, sname, sess) in st_assigns:
        d = doc_by_id[did]
        st = station_by_name[sname]
        if sname not in d.eligible_stations:
            violations.append(f"H3 doctor={did} not eligible for {sname}")
        if d.tier not in st.eligible_tiers:
            violations.append(f"H3 tier={d.tier} not allowed on {sname}")

    # H4 — oncall 1-in-3.
    oncall_days_by_doc: dict[int, set[int]] = {}
    for (did, day) in oncall:
        oncall_days_by_doc.setdefault(did, set()).add(day)
    for did in inst.prev_oncall:
        oncall_days_by_doc.setdefault(did, set()).add(-1)
    for did, days in oncall_days_by_doc.items():
        sorted_days = sorted(days)
        for i, a in enumerate(sorted_days):
            for b in sorted_days[i + 1:]:
                if b - a >= 3:
                    break
                violations.append(f"H4 doctor={did} oncall days {a} and {b} too close")

    # H5 — post-call off.
    for (did, day) in list(oncall) + [(d, -1) for d in inst.prev_oncall]:
        next_day = day + 1
        if next_day >= inst.n_days:
            continue
        any_work = False
        for (dd, dy, _, _) in st_assigns:
            if dd == did and dy == next_day:
                any_work = True
        if (did, next_day) in oncall or (did, next_day) in ext or (did, next_day) in wconsult:
            any_work = True
        if any_work:
            violations.append(f"H5 doctor={did} working on post-call day {next_day}")

    # H6 — senior on-call = no AM/PM.
    # H7 — junior on-call = no AM, PM==1 on weekdays.
    for (did, day) in oncall:
        d = doc_by_id[did]
        am = sum(1 for (dd, dy, _, sess) in st_assigns if dd == did and dy == day and sess == "AM")
        pm = sum(1 for (dd, dy, _, sess) in st_assigns if dd == did and dy == day and sess == "PM")
        if d.tier == "senior":
            if am != 0 or pm != 0:
                violations.append(f"H6 senior {did} on oncall day {day} AM={am} PM={pm}")
        elif d.tier == "junior":
            if am != 0:
                violations.append(f"H7 junior {did} on oncall day {day} AM={am} (should be 0)")
            if not inst.is_weekend(day) and pm != 1:
                violations.append(f"H7 junior {did} on oncall day {day} PM={pm} (should be 1)")

    # H8 — weekend coverage.
    for day in range(inst.n_days):
        if not inst.is_weekend(day):
            continue
        j_ext = sum(1 for (did, dy) in ext if dy == day and doc_by_id[did].tier == "junior")
        s_ext = sum(1 for (did, dy) in ext if dy == day and doc_by_id[did].tier == "senior")
        j_oc  = sum(1 for (did, dy) in oncall if dy == day and doc_by_id[did].tier == "junior")
        s_oc  = sum(1 for (did, dy) in oncall if dy == day and doc_by_id[did].tier == "senior")
        for want, got, label in ((1, j_ext, "junior_ext"), (1, s_ext, "senior_ext"),
                                  (1, j_oc, "junior_oncall"), (1, s_oc, "senior_oncall")):
            if want != got:
                violations.append(f"H8 day={day} {label}: {got} (want {want})")
        for ss in inst.subspecs:
            cnt = sum(1 for (did, dy) in wconsult
                      if dy == day and doc_by_id[did].subspec == ss)
            if cnt != 1:
                violations.append(f"H8 day={day} wconsult subspec={ss}: {cnt}")

    # H9 — every weekend-ext doctor gets a lieu day in {Fri before, Mon after}
    # (if either is in horizon). We verify existence of a no-work day with the
    # right weekday within 4 days.
    for (did, day) in ext:
        fri_before = None
        mon_after = None
        for dx in range(1, 5):
            t = day - dx
            if t < 0:
                break
            if inst.weekday_of(t) == 4:
                fri_before = t
                break
        for dx in range(1, 5):
            t = day + dx
            if t >= inst.n_days:
                break
            if inst.weekday_of(t) == 0:
                mon_after = t
                break
        candidates = [c for c in (fri_before, mon_after) if c is not None]
        if not candidates:
            continue  # no in-horizon candidate — spec says ok
        found_lieu = False
        for t in candidates:
            worked = any(dd == did and dy == t for (dd, dy, _, _) in st_assigns)
            if (did, t) in oncall or (did, t) in ext or (did, t) in wconsult:
                worked = True
            if not worked:
                found_lieu = True
                break
        if not found_lieu:
            violations.append(f"H9 doctor={did} ext day {day} has no lieu in {candidates}")

    # H10 — leave respected.
    for did, days in inst.leave.items():
        for t in days:
            if any(dd == did and dy == t for (dd, dy, _, _) in st_assigns):
                violations.append(f"H10 doctor={did} working on leave day {t}")
            if (did, t) in oncall or (did, t) in ext or (did, t) in wconsult:
                violations.append(f"H10 doctor={did} on role on leave day {t}")

    return violations


def scenario_baseline() -> Instance:
    return make_synthetic(n_doctors=30, n_days=28, seed=0)


def scenario_heavy_leave() -> Instance:
    return make_synthetic(n_doctors=30, n_days=28, seed=1, leave_rate=0.15)


def scenario_public_holidays() -> Instance:
    inst = make_synthetic(n_doctors=30, n_days=28, seed=2)
    inst.public_holidays.update({10, 11})  # mid-month 2-day holiday
    return inst


def scenario_sat_start() -> Instance:
    return make_synthetic(n_doctors=30, n_days=28, seed=3, start_weekday=5)


def scenario_higher_headcount() -> Instance:
    stations = tuple(replace(s, required_per_session=2) if s.name in ("US", "GEN_AM", "GEN_PM")
                     else s for s in DEFAULT_STATIONS)
    return make_synthetic(n_doctors=50, n_days=28, seed=4, stations=stations)


def scenario_prev_oncall() -> Instance:
    inst = make_synthetic(n_doctors=30, n_days=28, seed=5)
    # Pick the first junior and first senior as prev-oncall.
    j = next(d.id for d in inst.doctors if d.tier == "junior")
    s = next(d.id for d in inst.doctors if d.tier == "senior")
    inst.prev_oncall.update({j, s})
    return inst


def scenario_tight() -> Instance:
    return make_synthetic(n_doctors=20, n_days=28, seed=6)


def scenario_custom_stations() -> Instance:
    stations = (
        Station("CT", ("AM", "PM"), 1, frozenset({"consultant"})),
        Station("MR", ("AM", "PM"), 1, frozenset({"consultant"})),
        Station("US", ("AM", "PM"), 1, frozenset({"junior", "senior", "consultant"})),
        Station("XR_REPORT", ("AM", "PM"), 1,
                frozenset({"junior", "senior", "consultant"}), is_reporting=True),
        Station("NEURO_REPORT", ("AM", "PM"), 1,
                frozenset({"consultant"}), is_reporting=True),
        Station("IR", ("AM", "PM"), 1, frozenset({"consultant"})),
        Station("GEN_AM", ("AM",), 1, frozenset({"junior", "senior", "consultant"})),
        Station("GEN_PM", ("PM",), 1, frozenset({"junior", "senior", "consultant"})),
    )
    return make_synthetic(n_doctors=30, n_days=28, seed=7, stations=stations)


def scenario_short_horizon() -> Instance:
    return make_synthetic(n_doctors=30, n_days=3, seed=8, start_weekday=0)  # Mon-Wed, no weekend


def scenario_long_horizon() -> Instance:
    return make_synthetic(n_doctors=30, n_days=42, seed=9)


SCENARIOS = [
    ("A baseline",          scenario_baseline),
    ("B heavy_leave",       scenario_heavy_leave),
    ("C public_holidays",   scenario_public_holidays),
    ("D sat_start",         scenario_sat_start),
    ("E higher_headcount",  scenario_higher_headcount),
    ("F prev_oncall",       scenario_prev_oncall),
    ("G tight_N",           scenario_tight),
    ("H custom_stations",   scenario_custom_stations),
    ("I short_horizon",     scenario_short_horizon),
    ("J long_horizon",      scenario_long_horizon),
]


def main() -> int:
    print(f"{'scenario':<22} {'status':<10} {'time':>8} {'obj':>6}   violations")
    print("-" * 70)
    any_fail = False
    for label, fn in SCENARIOS:
        inst = fn()
        t0 = time.perf_counter()
        res = solve(inst, time_limit_s=90)
        dt = time.perf_counter() - t0
        viol = verify(inst, res)
        ok = "OK" if not viol else f"FAIL ({len(viol)})"
        obj = f"{int(res.objective)}" if res.objective is not None else "-"
        print(f"{label:<22} {res.status:<10} {dt:>7.2f}s {obj:>6}   {ok}")
        if viol:
            any_fail = True
            for v in viol[:5]:
                print(f"    - {v}")
    print("-" * 70)
    print("all scenarios passed" if not any_fail else "FAILURES — see above")
    return 0 if not any_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
