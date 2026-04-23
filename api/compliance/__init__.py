"""Regulatory-conformance checks layered on top of the hard-constraint
validator. The core model enforces H1–H15 (clinical / contractual
rules); this package enforces statutory rules like UK WTD or ACGME
duty hours that a roster must ALSO satisfy before it can be deployed.

See `docs/INDUSTRY_CONTEXT.md §5` for the rationale. The conformance
checks are reporting-only today: they don't feed back into the CP-SAT
model, they audit the produced roster. A failing check is visible to
the researcher but does not prevent the solve from returning.
"""

from api.compliance.uk_wtd import (
    WtdConfig,
    WtdViolation,
    check_uk_wtd,
)

__all__ = ["WtdConfig", "WtdViolation", "check_uk_wtd"]
