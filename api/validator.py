"""Standalone hard-constraint validator for a proposed assignment list.

The solver builds rosters that are hard-constraint-feasible by construction.
When a user manually edits a solved roster ("new version" workflow), we
need to report which constraints they've broken without re-invoking the
solver. This module walks the assignments and flags violations per rule.

Only hard constraints are checked. Soft penalties (fairness, idle weekdays,
preferences) are shown through the ObjectiveBreakdown panel on the Solve
page, not here.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from api.models.events import AssignmentRow
from api.models.session import SessionState


def validate(state: SessionState, assignments: list[AssignmentRow]) -> list[dict]:
    """Return a list of {rule, severity, location, message} violation dicts."""
    violations: list[dict] = []
    if not state.horizon.start_date or state.horizon.n_days <= 0:
        return [{
            "rule": "horizon",
            "severity": "error",
            "location": "",
            "message": "Horizon is not configured — can't validate.",
        }]

    start = state.horizon.start_date
    n_days = state.horizon.n_days
    dates = [start + timedelta(days=i) for i in range(n_days)]
    date_set = set(dates)

    doctors_by_name = {d.name: d for d in state.doctors}
    stations_by_name = {s.name: s for s in state.stations}
    public_holidays = set(state.horizon.public_holidays)
    subspecs = state.subspecs

    def is_weekend(d: date) -> bool:
        return d.weekday() >= 5 or d in public_holidays

    # ---------- index blocks (leave / no-X) ----------
    leave_dates: dict[str, set[date]] = defaultdict(set)
    no_oncall: dict[str, set[date]] = defaultdict(set)
    no_am: dict[str, set[date]] = defaultdict(set)
    no_pm: dict[str, set[date]] = defaultdict(set)
    for b in state.blocks:
        cur = b.date
        end = b.end_date or b.date
        while cur <= end:
            if cur in date_set:
                if b.type == "Leave":
                    leave_dates[b.doctor].add(cur)
                elif b.type == "No on-call":
                    no_oncall[b.doctor].add(cur)
                elif b.type == "No AM":
                    no_am[b.doctor].add(cur)
                elif b.type == "No PM":
                    no_pm[b.doctor].add(cur)
            cur += timedelta(days=1)

    # ---------- parse assignments ----------
    # by_slot[(date, station, session)] = [doctor names]
    by_slot: dict[tuple[date, str, str], list[str]] = defaultdict(list)
    # by_doc_date[(doctor, date)] = list of activity descriptors
    by_doc_date: dict[tuple[str, date], list[dict]] = defaultdict(list)

    for a in assignments:
        role = a.role.upper()
        if role.startswith("STATION_"):
            inner = role[len("STATION_"):]
            rsplit = inner.rsplit("_", 1)
            if len(rsplit) != 2:
                violations.append(_v("H3", "error", f"{a.doctor} {a.date}",
                                     f"Unparseable station role: {a.role}"))
                continue
            station, session = rsplit
            if session not in ("AM", "PM"):
                violations.append(_v("H3", "error", f"{a.doctor} {a.date}",
                                     f"Invalid session: {session}"))
                continue
            by_slot[(a.date, station, session)].append(a.doctor)
            by_doc_date[(a.doctor, a.date)].append(
                {"kind": "station", "station": station, "session": session}
            )
        elif role == "ONCALL":
            by_doc_date[(a.doctor, a.date)].append({"kind": "oncall"})
        elif role in ("WEEKEND_EXT", "EXT"):
            by_doc_date[(a.doctor, a.date)].append({"kind": "ext"})
        elif role in ("WEEKEND_CONSULT", "WCONSULT"):
            by_doc_date[(a.doctor, a.date)].append({"kind": "wconsult"})
        else:
            violations.append(_v("H3", "error", f"{a.doctor} {a.date}",
                                 f"Unknown role: {a.role}"))

    # ---------- H1 station coverage ----------
    for d in dates:
        we = is_weekend(d)
        for st in state.stations:
            if we and not state.constraints.weekend_am_pm:
                continue
            for sess in (st.sessions or []):
                count = len(by_slot.get((d, st.name, sess), []))
                if count != st.required_per_session:
                    severity = "error"
                    violations.append(_v(
                        "H1", severity,
                        f"{d.isoformat()} {st.name}/{sess}",
                        f"{count}/{st.required_per_session} people assigned.",
                    ))

    # ---------- H2 one station per session per person ----------
    for (doc, d), acts in by_doc_date.items():
        am = [a for a in acts if a.get("kind") == "station" and a.get("session") == "AM"]
        pm = [a for a in acts if a.get("kind") == "station" and a.get("session") == "PM"]
        if len(am) > 1:
            violations.append(_v("H2", "error", f"{doc} {d.isoformat()}",
                                 f"{len(am)} AM station assignments (max 1)."))
        if len(pm) > 1:
            violations.append(_v("H2", "error", f"{doc} {d.isoformat()}",
                                 f"{len(pm)} PM station assignments (max 1)."))

    # ---------- H3 eligibility ----------
    for (doc, d), acts in by_doc_date.items():
        person = doctors_by_name.get(doc)
        if not person:
            violations.append(_v("H3", "error", f"{doc} {d.isoformat()}",
                                 f"Unknown person '{doc}'."))
            continue
        for a in acts:
            if a.get("kind") != "station":
                continue
            sn = str(a.get("station") or "")
            stat = stations_by_name.get(sn)
            if not stat:
                violations.append(_v("H3", "error", f"{doc} {d.isoformat()}",
                                     f"Unknown station '{sn}'."))
                continue
            if sn not in (person.eligible_stations or []):
                violations.append(_v(
                    "H3", "error", f"{doc} {d.isoformat()}",
                    f"{doc} is not listed as eligible for {sn}.",
                ))
            if person.tier not in (stat.eligible_tiers or []):
                violations.append(_v(
                    "H3", "error", f"{doc} {d.isoformat()}",
                    f"{person.tier} can't work {sn} (tier not in eligible_tiers).",
                ))

    # ---------- H4 1-in-N on-call cap ----------
    if state.constraints.h4_enabled:
        N = state.constraints.h4_gap
        oncall_by_doc: dict[str, list[date]] = defaultdict(list)
        for (doc, d), acts in by_doc_date.items():
            if any(a.get("kind") == "oncall" for a in acts):
                oncall_by_doc[doc].append(d)
        for doc, ds in oncall_by_doc.items():
            ds_sorted = sorted(ds)
            for i in range(len(ds_sorted) - 1):
                gap = (ds_sorted[i + 1] - ds_sorted[i]).days
                if gap < N:
                    violations.append(_v(
                        "H4", "error", doc,
                        f"On-call on {ds_sorted[i]} and {ds_sorted[i + 1]} — only {gap} day(s) apart (need ≥{N}).",
                    ))

    # ---------- H5 post-call off ----------
    if state.constraints.h5_enabled:
        for (doc, d), acts in by_doc_date.items():
            if not any(a.get("kind") == "oncall" for a in acts):
                continue
            nxt = d + timedelta(days=1)
            if nxt not in date_set:
                continue
            next_acts = by_doc_date.get((doc, nxt), [])
            if next_acts:
                violations.append(_v(
                    "H5", "error", f"{doc} {nxt.isoformat()}",
                    f"{doc} was on-call {d.isoformat()}; should be off the next day but has assignment(s).",
                ))

    # ---------- H8 weekend coverage ----------
    if state.constraints.h8_enabled:
        for d in dates:
            if not is_weekend(d):
                continue
            j_oc = j_ext = s_oc = s_ext = 0
            wc_by_ss: dict[str, int] = defaultdict(int)
            for (doc, dd), acts in by_doc_date.items():
                if dd != d:
                    continue
                person = doctors_by_name.get(doc)
                if not person:
                    continue
                for a in acts:
                    if a.get("kind") == "oncall":
                        if person.tier == "junior":
                            j_oc += 1
                        elif person.tier == "senior":
                            s_oc += 1
                    elif a.get("kind") == "ext":
                        if person.tier == "junior":
                            j_ext += 1
                        elif person.tier == "senior":
                            s_ext += 1
                    elif a.get("kind") == "wconsult":
                        if person.tier == "consultant" and person.subspec:
                            wc_by_ss[person.subspec] += 1
            if j_oc != 1:
                violations.append(_v("H8", "error", d.isoformat(),
                                     f"{j_oc} junior on-call (need 1)."))
            if s_oc != 1:
                violations.append(_v("H8", "error", d.isoformat(),
                                     f"{s_oc} senior on-call (need 1)."))
            if j_ext != 1:
                violations.append(_v("H8", "error", d.isoformat(),
                                     f"{j_ext} junior EXT (need 1)."))
            if s_ext != 1:
                violations.append(_v("H8", "error", d.isoformat(),
                                     f"{s_ext} senior EXT (need 1)."))
            for ss in subspecs:
                if wc_by_ss.get(ss, 0) != 1:
                    violations.append(_v(
                        "H8", "error", f"{d.isoformat()} ({ss})",
                        f"{wc_by_ss.get(ss, 0)} {ss} consultant (need 1).",
                    ))

    # ---------- Weekday on-call coverage ----------
    if state.constraints.weekday_oncall_coverage:
        for d in dates:
            if is_weekend(d):
                continue
            j_oc = s_oc = 0
            for (doc, dd), acts in by_doc_date.items():
                if dd != d:
                    continue
                person = doctors_by_name.get(doc)
                if not person:
                    continue
                if any(a.get("kind") == "oncall" for a in acts):
                    if person.tier == "junior":
                        j_oc += 1
                    elif person.tier == "senior":
                        s_oc += 1
            if j_oc != 1:
                violations.append(_v(
                    "weekday_oc", "error", d.isoformat(),
                    f"{j_oc} junior on-call weekday (need 1).",
                ))
            if s_oc != 1:
                violations.append(_v(
                    "weekday_oc", "error", d.isoformat(),
                    f"{s_oc} senior on-call weekday (need 1).",
                ))

    # ---------- H10 leave ----------
    for doc, leaves in leave_dates.items():
        for d in leaves:
            if by_doc_date.get((doc, d)):
                violations.append(_v(
                    "H10", "error", f"{doc} {d.isoformat()}",
                    f"{doc} is on leave but has assignment(s).",
                ))

    # ---------- H12 no-oncall block ----------
    for doc, blocked in no_oncall.items():
        for d in blocked:
            acts = by_doc_date.get((doc, d), [])
            if any(a.get("kind") == "oncall" for a in acts):
                violations.append(_v(
                    "H12", "error", f"{doc} {d.isoformat()}",
                    f"{doc} has 'No on-call' block but is scheduled on-call.",
                ))

    # ---------- H13 session block ----------
    for doc, blocked in no_am.items():
        for d in blocked:
            acts = by_doc_date.get((doc, d), [])
            if any(a.get("kind") == "station" and a.get("session") == "AM" for a in acts):
                violations.append(_v(
                    "H13", "error", f"{doc} {d.isoformat()}",
                    f"{doc} has 'No AM' block but has AM assignment.",
                ))
    for doc, blocked in no_pm.items():
        for d in blocked:
            acts = by_doc_date.get((doc, d), [])
            if any(a.get("kind") == "station" and a.get("session") == "PM" for a in acts):
                violations.append(_v(
                    "H13", "error", f"{doc} {d.isoformat()}",
                    f"{doc} has 'No PM' block but has PM assignment.",
                ))

    return violations


def _v(rule: str, severity: str, location: str, message: str) -> dict:
    return {
        "rule": rule,
        "severity": severity,
        "location": location,
        "message": message,
    }
