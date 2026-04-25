"""Standalone hard-constraint validator for a proposed assignment list.

The solver builds rosters that are hard-constraint-feasible by construction.
When a user manually edits a solved roster ("new version" workflow), we
need to report which constraints they've broken without re-invoking the
solver. This module walks the assignments and flags violations per rule.

Only hard constraints are checked. Soft penalties (fairness, idle weekdays,
preferences) are shown through the ObjectiveBreakdown panel on the Solve
page, not here.

Phase B: on-call rules are user-defined per-OnCallType, not the legacy
fixed `oncall` / `ext` / `wconsult` triple. This validator iterates
`state.on_call_types` and checks each type's `daily_required`,
`frequency_cap_days`, `next_day_off`, `works_full_day`, `works_pm_only`
against the proposed roster. Legacy role strings (`ONCALL`, `WEEKEND_EXT`,
`WEEKEND_CONSULT`) are accepted and resolved against any type whose
`legacy_role_alias` matches and whose advisory `eligible_tiers` includes
the doctor's tier.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from api.models.events import AssignmentRow
from api.models.session import OnCallType, SessionState

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


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
    on_call_types = list(state.on_call_types)
    types_by_key = {t.key: t for t in on_call_types}

    def is_weekend(d: date) -> bool:
        return d.weekday() >= 5 or d in public_holidays

    def day_active_for_type(d: date, t: OnCallType) -> bool:
        wd = WEEKDAY_NAMES[d.weekday()]
        if wd in t.days_active:
            return True
        if d in public_holidays and ("Sat" in t.days_active or "Sun" in t.days_active):
            return True
        return False

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
    by_slot: dict[tuple[date, str, str], list[str]] = defaultdict(list)
    by_doc_date: dict[tuple[str, date], list[dict]] = defaultdict(list)

    def _resolve_oncall_type(doc_name: str, alias: str) -> str | None:
        """Map a legacy alias literal to a unique type key the doctor is
        eligible for. Returns None on miss / ambiguous."""
        person = doctors_by_name.get(doc_name)
        if not person:
            return None
        candidates = [
            t.key for t in on_call_types
            if t.legacy_role_alias == alias
            and (not person.eligible_oncall_types
                 or t.key in person.eligible_oncall_types)
        ]
        if len(candidates) == 1:
            return candidates[0]
        # Fallback: filter further by advisory tier match.
        tier_filtered = [
            k for k in candidates
            if person.tier in (types_by_key[k].eligible_tiers or [])
        ]
        if len(tier_filtered) == 1:
            return tier_filtered[0]
        # Couldn't disambiguate — return first candidate if any.
        return candidates[0] if candidates else None

    LEGACY_ALIASES = {
        "ONCALL": "ONCALL",
        "WEEKEND_EXT": "WEEKEND_EXT",
        "EXT": "WEEKEND_EXT",
        "WEEKEND_CONSULT": "WEEKEND_CONSULT",
        "WCONSULT": "WEEKEND_CONSULT",
    }

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
            continue
        if role.startswith("ONCALL_"):
            type_key = role[len("ONCALL_"):]
            if type_key not in types_by_key:
                violations.append(_v("H3", "error", f"{a.doctor} {a.date}",
                                     f"Unknown on-call type: {type_key}"))
                continue
            by_doc_date[(a.doctor, a.date)].append(
                {"kind": "oncall", "type_key": type_key}
            )
            continue
        alias = LEGACY_ALIASES.get(role)
        if alias:
            type_key = _resolve_oncall_type(a.doctor, alias)
            if type_key is None:
                violations.append(_v(
                    "H3", "error", f"{a.doctor} {a.date}",
                    f"Could not resolve {a.role} to a defined on-call type "
                    f"for {a.doctor}.",
                ))
                continue
            by_doc_date[(a.doctor, a.date)].append(
                {"kind": "oncall", "type_key": type_key, "alias": alias}
            )
            continue
        violations.append(_v("H3", "error", f"{a.doctor} {a.date}",
                             f"Unknown role: {a.role}"))

    # ---------- H1 station coverage ----------
    for d in dates:
        we = is_weekend(d)
        for st in state.stations:
            if we and not st.weekend_enabled:
                continue
            if not we and not st.weekday_enabled:
                continue
            sessions = st.sessions or []
            is_full_day = "FULL_DAY" in sessions
            if is_full_day:
                am_holders = by_slot.get((d, st.name, "AM"), [])
                pm_holders = by_slot.get((d, st.name, "PM"), [])
                count = len(am_holders)
                if count != st.required_per_session:
                    violations.append(_v(
                        "H1", "error",
                        f"{d.isoformat()} {st.name}/FULL_DAY",
                        f"{count}/{st.required_per_session} people assigned.",
                    ))
                if set(am_holders) != set(pm_holders):
                    violations.append(_v(
                        "H1", "error",
                        f"{d.isoformat()} {st.name}/FULL_DAY",
                        (
                            f"FULL_DAY pairing broken: AM={sorted(am_holders)} "
                            f"vs PM={sorted(pm_holders)}. Both halves must be "
                            f"the same doctor."
                        ),
                    ))
                continue
            for sess in sessions:
                count = len(by_slot.get((d, st.name, sess), []))
                if count != st.required_per_session:
                    violations.append(_v(
                        "H1", "error",
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
        # Mutual exclusion: at most one on-call type per (doctor, day).
        oncall_types_today = [a for a in acts if a.get("kind") == "oncall"]
        if len(oncall_types_today) > 1:
            keys = [a.get("type_key") for a in oncall_types_today]
            violations.append(_v(
                "H2", "error", f"{doc} {d.isoformat()}",
                f"{len(oncall_types_today)} on-call types assigned "
                f"({sorted(set(keys))}); a doctor may hold at most one per day.",
            ))

    # ---------- H3 station eligibility ----------
    for (doc, d), acts in by_doc_date.items():
        person = doctors_by_name.get(doc)
        if not person:
            violations.append(_v("H3", "error", f"{doc} {d.isoformat()}",
                                 f"Unknown person '{doc}'."))
            continue
        for a in acts:
            if a.get("kind") == "station":
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
            elif a.get("kind") == "oncall":
                type_key = str(a.get("type_key") or "")
                if (person.eligible_oncall_types
                        and type_key not in person.eligible_oncall_types):
                    violations.append(_v(
                        "H3", "error", f"{doc} {d.isoformat()}",
                        f"{doc} is not listed as eligible for on-call type {type_key}.",
                    ))

    # ---------- H4 per-OnCallType 1-in-N cap ----------
    for t in on_call_types:
        N = t.frequency_cap_days
        if N is None or N < 2:
            continue
        type_dates_by_doc: dict[str, list[date]] = defaultdict(list)
        for (doc, d), acts in by_doc_date.items():
            for a in acts:
                if a.get("kind") == "oncall" and a.get("type_key") == t.key:
                    type_dates_by_doc[doc].append(d)
        for doc, ds in type_dates_by_doc.items():
            ds_sorted = sorted(ds)
            for i in range(len(ds_sorted) - 1):
                gap = (ds_sorted[i + 1] - ds_sorted[i]).days
                if gap < N:
                    violations.append(_v(
                        "H4", "error", doc,
                        f"On-call type {t.key} on {ds_sorted[i]} and "
                        f"{ds_sorted[i + 1]} — only {gap} day(s) apart "
                        f"(need ≥{N}).",
                    ))

    # ---------- H5 per-OnCallType post-shift rest ----------
    if state.constraints.h5_enabled:
        for t in on_call_types:
            if not t.next_day_off:
                continue
            for (doc, d), acts in by_doc_date.items():
                if not any(a.get("kind") == "oncall" and a.get("type_key") == t.key
                           for a in acts):
                    continue
                nxt = d + timedelta(days=1)
                if nxt not in date_set:
                    continue
                next_acts = by_doc_date.get((doc, nxt), [])
                if next_acts:
                    violations.append(_v(
                        "H5", "error", f"{doc} {nxt.isoformat()}",
                        f"{doc} was on-call ({t.key}) {d.isoformat()}; "
                        f"should be off the next day but has assignment(s).",
                    ))

    # ---------- H6/H7 per-OnCallType day-of pattern ----------
    for t in on_call_types:
        if not (t.works_full_day or t.works_pm_only):
            continue
        for (doc, d), acts in by_doc_date.items():
            if not any(a.get("kind") == "oncall" and a.get("type_key") == t.key
                       for a in acts):
                continue
            am = [a for a in acts if a.get("kind") == "station" and a.get("session") == "AM"]
            pm = [a for a in acts if a.get("kind") == "station" and a.get("session") == "PM"]
            if t.works_full_day:
                if am or pm:
                    violations.append(_v(
                        "H6", "error", f"{doc} {d.isoformat()}",
                        f"{doc} on {t.key} ({t.label or t.key}) must have "
                        f"no AM/PM (works_full_day=True); got AM={len(am)}, PM={len(pm)}.",
                    ))
            elif t.works_pm_only:
                if am:
                    violations.append(_v(
                        "H7", "error", f"{doc} {d.isoformat()}",
                        f"{doc} on {t.key} must have no AM (works_pm_only); got {len(am)}.",
                    ))
                if not is_weekend(d) and len(pm) != 1:
                    violations.append(_v(
                        "H7", "error", f"{doc} {d.isoformat()}",
                        f"{doc} on {t.key} must have exactly 1 PM "
                        f"(works_pm_only, weekday); got {len(pm)}.",
                    ))

    # ---------- H8 per-OnCallType daily_required ----------
    for t in on_call_types:
        if t.daily_required <= 0:
            continue
        for d in dates:
            if not day_active_for_type(d, t):
                continue
            count = 0
            for (doc, dd), acts in by_doc_date.items():
                if dd != d:
                    continue
                for a in acts:
                    if a.get("kind") == "oncall" and a.get("type_key") == t.key:
                        count += 1
            if count != t.daily_required:
                violations.append(_v(
                    "H8", "error", f"{d.isoformat()} {t.key}",
                    f"{count} doctor(s) on {t.key} (need {t.daily_required}).",
                ))

    # ---------- H9 lieu day (per-type, weekend-role types only) ----------
    if state.constraints.h9_enabled:
        for t in on_call_types:
            if not t.counts_as_weekend_role:
                continue
            if t.works_full_day or t.works_pm_only:
                continue
            for (doc, d), acts in by_doc_date.items():
                if not any(a.get("kind") == "oncall" and a.get("type_key") == t.key
                           for a in acts):
                    continue
                if not is_weekend(d):
                    continue
                # Look for a no-work day at Fri-before or Mon-after.
                fri_before = None
                mon_after = None
                for dx in range(1, 8):
                    cand = d - timedelta(days=dx)
                    if cand in date_set and cand.weekday() == 4:
                        fri_before = cand
                        break
                for dx in range(1, 8):
                    cand = d + timedelta(days=dx)
                    if cand in date_set and cand.weekday() == 0:
                        mon_after = cand
                        break
                candidates = [c for c in (fri_before, mon_after) if c is not None]
                if not candidates:
                    continue
                if any(not by_doc_date.get((doc, c)) for c in candidates):
                    continue  # got a free day
                violations.append(_v(
                    "H9", "error", f"{doc} {d.isoformat()}",
                    f"{doc} did {t.key} on {d.isoformat()} but has no lieu "
                    f"day in {[c.isoformat() for c in candidates]}.",
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
