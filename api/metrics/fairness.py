"""FTE-aware fairness / bias metrics for a solved roster.

Formulae follow `docs/RESEARCH_METRICS.md §4`. Each doctor's raw weighted
workload `S_d` is divided by their FTE `f_d` before aggregation so a
0.5-FTE doctor doing 50% of the work scores the same as a full-timer
doing 100%. Metrics are reported per-tier because cross-tier comparisons
(junior vs consultant) are meaningless.

Reports both Gini (our existing convention) and CV (standard in NRP
literature; see `docs/INDUSTRY_CONTEXT.md §3`) so downstream analysis
is cross-comparable with both econ-flavoured and OR-flavoured papers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import median, pstdev
from typing import Any

from api.models.events import AssignmentRow
from api.models.session import SessionState, WorkloadWeights

_DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ------------------------------------------------------------- helpers

def _is_weekend(d: date, holidays: set[date]) -> bool:
    return d.weekday() >= 5 or d in holidays


def _role_kind(role: str) -> tuple[str, str | None]:
    """Map an AssignmentRow.role to (kind, session). `session` is only
    non-None for station roles. Phase B: any `ONCALL_<key>` (user-
    defined on-call type) is treated as `oncall` for fairness bucketing."""
    r = role.upper()
    if r.startswith("STATION_"):
        parts = r[len("STATION_"):].rsplit("_", 1)
        if len(parts) == 2 and parts[1] in ("AM", "PM"):
            return "station", parts[1]
        return "station", None
    if r == "ONCALL" or r.startswith("ONCALL_"):
        return "oncall", None
    if r in ("WEEKEND_EXT", "EXT"):
        return "ext", None
    if r in ("WEEKEND_CONSULT", "WCONSULT"):
        return "wconsult", None
    return "unknown", None


def _role_weight(kind: str, is_weekend: bool, w: WorkloadWeights) -> int:
    if kind == "station":
        return w.weekend_session if is_weekend else w.weekday_session
    if kind == "oncall":
        return w.weekend_oncall if is_weekend else w.weekday_oncall
    if kind == "ext":
        return w.weekend_ext
    if kind == "wconsult":
        return w.weekend_consult
    return 0


# ------------------------------------------------------------- aggregates

def _gini(values: list[float]) -> float:
    """Gini coefficient. 0 = perfect equality, 1 = one-person-has-all.

    Uses the mean-absolute-difference formula:
        G = Σ_i Σ_j |x_i − x_j| / (2 n² μ)
    """
    n = len(values)
    if n == 0:
        return 0.0
    mu = sum(values) / n
    if mu <= 0:
        return 0.0
    mad = sum(abs(a - b) for a in values for b in values) / (n * n)
    return round(mad / (2.0 * mu), 4)


def _summary(values: list[float]) -> dict[str, Any]:
    """Range / CV / Gini / std / mean over a list of FTE-normalised scores."""
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": 0.0, "range": 0.0, "cv": 0.0, "gini": 0.0, "std": 0.0}
    mean_v = sum(values) / n
    std_v = pstdev(values) if n > 1 else 0.0
    return {
        "n": n,
        "mean": round(mean_v, 2),
        "range": round((max(values) - min(values)) if values else 0.0, 2),
        "cv": round(std_v / mean_v, 4) if mean_v > 0 else 0.0,
        "gini": _gini(values),
        "std": round(std_v, 2),
    }


# ------------------------------------------------------------- public API

def compute_fairness(
    state: SessionState,
    assignments: list[AssignmentRow],
) -> dict[str, Any]:
    """Compute FTE-aware fairness metrics over a list of AssignmentRows.

    Returns a JSON-serialisable dict with:
      - per_tier: summary metrics for total weighted workload, per tier
      - per_tier_oncall: same but restricted to on-call assignments
      - per_individual: per-doctor breakdown with delta-from-median
      - dow_load: weighted-workload distribution per tier × day-of-week
    """
    horizon = state.horizon
    w = state.workload_weights
    holidays = set(horizon.public_holidays or [])

    doctors_by_name = {d.name: d for d in state.doctors}
    # Initialise zeroed rows for every doctor so the UI can render them
    # even if they got no assignments.
    per_doc: dict[str, dict[str, Any]] = {}
    for d in state.doctors:
        per_doc[d.name] = {
            "doctor": d.name,
            "tier": d.tier,
            "fte": float(d.fte or 1.0),
            "weighted_workload": 0,
            "oncall_workload": 0,
            "oncall_count": 0,
            "weekend_count": 0,
            "station_count": 0,
        }

    # dow_load[tier][dow_label] → total weighted workload.
    dow_load: dict[str, dict[str, int]] = {
        t: {lbl: 0 for lbl in _DOW_LABELS}
        for t in ("junior", "senior", "consultant")
    }

    for a in assignments:
        doc = doctors_by_name.get(a.doctor)
        if not doc:
            continue
        kind, _sess = _role_kind(a.role)
        if kind == "unknown":
            continue
        we = _is_weekend(a.date, holidays)
        weight = _role_weight(kind, we, w)
        row = per_doc[a.doctor]
        row["weighted_workload"] += weight
        dow_load[doc.tier][_DOW_LABELS[a.date.weekday()]] += weight
        if kind == "oncall":
            row["oncall_workload"] += weight
            row["oncall_count"] += 1
            if we:
                row["weekend_count"] += 1
        elif kind == "station":
            row["station_count"] += 1
        elif kind in ("ext", "wconsult"):
            row["weekend_count"] += 1

    # Per-individual: FTE-normalised workload, delta from tier median.
    by_tier: dict[str, list[str]] = defaultdict(list)
    for name, row in per_doc.items():
        by_tier[row["tier"]].append(name)
        fte = row["fte"] if row["fte"] > 0 else 1.0
        row["fte_normalised"] = round(row["weighted_workload"] / fte, 2)

    for tier, names in by_tier.items():
        values = [per_doc[n]["fte_normalised"] for n in names]
        tier_median = median(values) if values else 0.0
        for n in names:
            per_doc[n]["delta_from_median"] = round(
                per_doc[n]["fte_normalised"] - tier_median, 2
            )

    # Per-tier summaries (total + oncall only).
    per_tier = {}
    per_tier_oncall = {}
    for tier, names in by_tier.items():
        values = [per_doc[n]["fte_normalised"] for n in names]
        per_tier[tier] = _summary(values)
        oncall_values = [
            per_doc[n]["oncall_workload"] / (per_doc[n]["fte"] or 1.0)
            for n in names
        ]
        per_tier_oncall[tier] = _summary(
            [round(v, 2) for v in oncall_values]
        )

    # Tier order for rendering. Keep the literal tier keys so the UI can
    # join on `tier_labels` for display.
    tier_order = ["junior", "senior", "consultant"]

    return {
        "tier_order": tier_order,
        "per_tier": per_tier,
        "per_tier_oncall": per_tier_oncall,
        "per_individual": sorted(
            per_doc.values(),
            key=lambda r: (tier_order.index(r["tier"]) if r["tier"] in tier_order else 99,
                           -r["fte_normalised"]),
        ),
        "dow_load": dow_load,
        "horizon_days": horizon.n_days,
    }
