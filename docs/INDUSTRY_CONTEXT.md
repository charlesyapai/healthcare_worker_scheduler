# Industry Context — Healthcare Workforce Scheduling

**Status:** Literature-grounded background for the validation agent.
Last updated 2026-04-23.

This document positions our solver inside the published literature and
real-world deployment landscape. Read it before [`VALIDATION_PLAN.md`](VALIDATION_PLAN.md)
so the metrics and benchmarks you build map onto what the field
actually expects.

> **Source caveat:** the literature summary below was synthesised by a
> research agent without live web access. Treat URLs as verification
> targets. Before publication, every cited paper / benchmark URL must be
> independently confirmed and any uncertain claim re-checked against
> Google Scholar. Annotations marked **[verify]** flag specific items
> needing this audit.

---

## 1. The problem this solver solves — proper name

In the academic literature this class of problem is the
**Nurse Rostering Problem (NRP)** when the team is fixed and the
horizon is a few weeks. Adjacent / overlapping terminology:

- **Nurse Scheduling Problem (NSP)** — older synonym, more common in
  US/MILP work (Jaumard, Semet, Vovor 1998).
- **Physician Scheduling / Resident Scheduling** — distinct
  sub-literature; smaller teams, heavier rotation/training rules,
  different regulatory layer (ACGME).
- **Personnel / Workforce / Staff Scheduling** — umbrella terms used
  in survey papers; Ernst et al. (2004) coined "staff scheduling and
  rostering" as the canonical umbrella.
- **Shift Scheduling** — narrower; "which shift patterns to run" rather
  than "who works which shift". Don't confuse with NRP.

**For our purposes:** we solve a generalised NRP that supports both
nursing (3-tier ward staff) and physician (junior/senior/consultant)
rotas via configurable tier labels and station definitions. The
validation plan should consistently use **"Nurse Rostering Problem
(NRP)" as the umbrella term** in publication-facing materials, with a
note that it is generalised to physician scheduling via the tier-label
abstraction.

### Canonical surveys to cite

- Burke, De Causmaecker, Vanden Berghe, Van Landeghem (2004). *The
  State of the Art of Nurse Rostering.* J. Scheduling 7(6):441–499.
  **[verify]** — the foundational reference.
- Ernst, Jiang, Krishnamoorthy, Sier (2004). *Staff scheduling and
  rostering: A review of applications, methods and models.* European
  J. Operational Research 153(1):3–27. **[verify]**
- Cheang, Li, Lim, Rodrigues (2003). *Nurse rostering problems – a
  bibliographic survey.* EJOR 151(3):447–460. **[verify]**
- Van den Bergh et al. (2013). *Personnel scheduling: A literature
  review.* EJOR 226(3):367–385. **[verify]**

More recent (post-2020) reviews exist but the field has not produced a
single dominant survey yet. Our validation plan should cite the
classics plus a fresh Google-Scholar pass at submission time.

---

## 2. Public benchmarks we can use

| Benchmark | Source | Format | Licence (verify) | Notes |
|---|---|---|---|---|
| **Curtois NRP collection** | Tim Curtois, U. Nottingham; `cs.nott.ac.uk/~psztc/NRP/` **[verify URL]** | Custom plain-text per-instance family | Academic free; some real-hospital data is anonymised | Most-cited modern aggregator. Includes BCV, Musa, Ozkarahan, Valouxis, GPost variants. **Adopt first.** |
| **INRC-II (2014–15)** | Second International Nurse Rostering Competition | JSON instances + a competition-grade validator binary | Free for research | Rolling-horizon problem; provides the de-facto **common-currency penalty score** so reporting against INRC-II makes us instantly comparable to ~20+ published papers. **Adopt for headline numbers.** |
| **INRC-I (2010)** | First INRC, KU Leuven CODeS group | XML + validator | Free for research | Older, simpler horizon model; useful as a regression check. |
| **NSPLib** | Vanhoucke & Maenhout (2007/2009), Ghent. `nsplib.ugent.be` **[verify URL]** | Plain text, custom | Academic free; weak explicit licence | 9000+ instances parameterised by nurses × days × skills. Good for **scaling-curve** experiments. |
| **Schaerf instances** | Università di Udine | — | Free | Adjacent to Curtois; check overlap before duplicating. |

**Recommendation:** start with **Curtois (breadth + diversity) + INRC-II
(comparability + headline number)**. NSPLib if scaling experiments
need parameter-sweep control. Skip everything else for v1.

---

## 3. Standard metrics used in the field

Beyond what we already track:

**Quality (already emitted by our SolveResult):**
- INRC-II / Curtois soft-constraint **penalty score** (the de-facto
  common currency).
- **Optimality gap** vs LP relaxation lower bound (more meaningful in
  MIP literature; CP-SAT bound is structurally loose for NRP — see
  RESEARCH_METRICS §1.3).
- **% instances solved to proven optimality** within a fixed time
  budget (table-stakes for competition-style reporting).

**Anytime-algorithm reporting (CP-SAT-friendly):**
- Time-to-first-feasible.
- Time-to-best.
- Convergence curve (objective vs wall time).

**Fairness / workload distribution:**
- **Coefficient of variation (CV)** of assigned hours, weekend shifts,
  night shifts per nurse — most common in literature.
- **Range** (max − min) of unwanted-shift counts.
- **Jain's fairness index** — common in scheduling/networking, less
  standard in NRP but defensible.
- **Theil index** — occasionally cited; econ-flavoured.
- **Number of preference violations per nurse** (mean, max, distribution).
- **Gini coefficient** — what we currently use; note that NRP papers
  often prefer CV. We should report **both** so we're cross-comparable
  with multiple paper styles.

**Operational / clinical:**
- **Coverage shortfall** (under-staffed shift-hours) and
  **over-coverage** (paid idle).
- **Skill-mix violations** (ratio of senior:junior on shift below
  threshold).
- **Consecutive-night and rest-period violations.**

**Robustness (rolling-horizon, important for INRC-II):**
- **Reschedule churn** — # assignments changed when re-solving with new info.
- **Cost of stochasticity** — expected vs deterministic objective gap.

**Implication for `RESEARCH_METRICS.md`:** add CV alongside Gini, add
INRC-II penalty as a first-class metric, add coverage shortfall and
over-coverage as separate metrics from idle-weekday count.

---

## 4. Constraint taxonomy — does our H1–H15 fit?

The literature classifies constraints along multiple axes:

- **Hard vs soft** (universal binary). Hard = legal / contractual;
  soft = preference / quality, weighted into the objective.
- **De Causmaecker & Vanden Berghe**: *coverage*, *time-related*,
  *succession*, *fairness*, *preference*, *skill*.
- **Ernst et al. (2004)**: *demand modelling, days off, shift
  scheduling, line-of-work construction, task assignment, staff
  assignment* — process-oriented.
- **Curtois benchmark**: *contracts, cover requirements, patterns,
  requests*.

**Our H1–H15 mapped to De Causmaecker / Vanden Berghe:**

| Our rule | Their category |
|---|---|
| H1 station coverage | coverage |
| H2 one station per session | structural |
| H3 station eligibility | skill |
| H4 1-in-N on-call cap | time-related (succession) |
| H5 post-call off | succession |
| H6 senior-on-call full off | succession |
| H7 junior-on-call PM | succession |
| H8 weekend coverage | coverage |
| H9 lieu day | time-related |
| H10 leave | preference (hard) |
| H11 mandatory weekday (soft S5) | fairness / utilisation |
| H12 no-on-call block | preference (hard) |
| H13 session block | preference (hard) |
| H14 max on-calls per doctor | time-related |
| H15 manual overrides | external |
| weekday on-call coverage | coverage |

**Verdict:** our taxonomy is mainstream. The validation plan should
include a one-page **"H-rule → standard taxonomy"** mapping table in
the publication so reviewers can see we're not inventing a parallel
universe.

---

## 5. Regulatory context — what "feasible" really means

A roster that is mathematically feasible but violates statutory limits
is unusable in production. Three jurisdictions worth supporting:

### UK — junior doctors' 2016 contract + EU WTD

- Max 48 hr/week averaged over the reference period (with opt-out).
- Max 72 hr in any 7 days.
- Max 13 hr/shift.
- ≥11 hr rest between shifts.
- Max 4 consecutive long days, max 7 consecutive nights.
- "Exception reports" mechanism for breaches.
- WTD 2003/88/EC: 48-hr weekly average, 11-hr daily rest, 24-hr weekly
  rest. SIMAP (2000) and Jaeger (2003) ECJ rulings: **on-call time at
  workplace counts as working time** — major impact on physician
  schedules.

### US — ACGME duty hours for residents

- ≤80 hr/week averaged over 4 weeks.
- ≤24+4 hr continuous.
- ≥1 day off in 7.
- ≥8 hr between shifts (14 after a 24-hr call).
- 2017 revision relaxed PGY-1 16-hr cap.

### US — California AB394 nurse-staffing ratios

- 1:2 ICU, 1:5 med-surg, etc. The only state with hard-mandated
  nurse:patient ratios. Other states have committee-based or
  disclosure-only regimes.

### Other relevant frameworks

- **FLSA** overtime rules.
- **Collective bargaining** agreements (NYSNA in NY, etc.) often
  specify weekend frequency and cancellation notice.
- **The Joint Commission** standards on fatigue management.
- **NHS Agenda for Change** (UK) for nursing — working time, unsocial
  hours premia.

**Implication for validation:** the Lab tab should support a
**regulatory-conformance test suite** as a pluggable hard-constraint
module. Pick one jurisdiction (suggest UK NHS junior-doctor + WTD for
academic publication audience; ACGME for US reach) and codify it as a
deterministic test. Then the validation report can claim "passes UK
WTD conformance" or "passes ACGME duty-hour conformance" — a
concrete, defensible claim.

---

## 6. Solution methods we should compare against

Typical baseline ladder in NRP papers:

1. **Construction heuristics:** greedy, list scheduling — sanity floor.
2. **MILP** via CPLEX/Gurobi (or open-source PuLP+CBC for
   reproducibility) on a direct formulation. Hits memory limits beyond
   ~30 nurses × 28 days but is the "is anyone doing better than
   textbook OR?" baseline.
3. **Decomposition:** column generation / branch-and-price (Jaumard et
   al., Maenhout & Vanhoucke). Strong on large instances.
4. **Metaheuristics:** simulated annealing, tabu, VNS, LNS, GA,
   memetic, scatter, hyper-heuristics (Burke's Nottingham group).
5. **Constraint Programming:** OPL, Choco, Gecode; **CP-SAT (OR-Tools)**
   is the strong post-2018 baseline — Google's solver has won MiniZinc
   challenges and is the natural comparator for our work.
6. **Hybrids:** CP+LNS (extremely effective on INRC instances),
   matheuristics.
7. **ML / RL:** still nascent in NRP; some 2021+ papers use RL but no
   dominant approach.

**Recommended baselines for our validation plan (in priority order):**

1. **PuLP + CBC MILP** on a direct formulation. Open-source,
   reproducible, free of commercial-licence concerns. Gives the
   "naive textbook OR" baseline.
2. **CP-SAT with naive encoding** (no warm-start, no presolve tuning)
   to show the lift of our enhanced configuration.
3. **Best published INRC-II solver scores** — paper comparison only,
   no re-implementation. Cite Bilgin et al., Stølevik et al., etc.
4. **Optional simple SA implementation** as a metaheuristic
   representative if reviewer feedback asks for one.

---

## 7. Recent (2020–2025) trends to be aware of

- **Explicit fairness objectives:** multi-objective formulations with
  Gini / max-min as first-class objectives, not just penalties. Health
  Care Management Science and J. Scheduling are the relevant venues.
- **Stochastic / robust NRP:** demand uncertainty, absenteeism.
  Restrepo, Lusby, Maenhout active here.
- **Real-time / rolling-horizon rescheduling:** disruption recovery;
  minimise edit distance to the original roster.
- **COVID-era flexibility:** redeployment across wards, rapid
  re-skilling, cohorting (infection-control: same staff to same
  patients). Several 2020–2022 papers; not yet consolidated.
- **Multi-skill / cross-training:** explicit skill-substitution graphs.
- **ML/RL:** mainly demand-forecasting feeding deterministic
  optimisers; pure RL solvers remain experimental.
- **Explainability / preference elicitation:** small but growing.
- **Self-rostering / preference-based:** participatory designs;
  RotaGeek-style.

**Implications:** a paper today should at minimum address fairness
explicitly (we already do — Score breakdown), include preference
handling (we do via S6), and either claim or disclaim rolling-horizon
support (we currently don't — flag as future work, don't claim it).

---

## 8. Commercial tools — what the industry actually buys

Not competitors per se, but useful to understand what real procurement
expects. Brief feature-set survey:

- **UKG (Kronos) Healthcare / Workforce Dimensions:** demand
  forecasting, self-scheduling, time-and-attendance, credential
  tracking, mobile shift-swap. Heavy on compliance reporting (FLSA,
  union rules).
- **QGenda** (US, large physician/anaesthesia market): rules-based
  auto-generation, on-call management, credentialing, compensation
  tracking. Marketed as "physician-led scheduling".
- **RotaGeek** (UK): NHS-focused, demand-led rostering, employee app,
  AI-assisted suggestions, e-Rostering compliance.
- **Allocate Software / RLDatix HealthRoster:** dominant in NHS —
  important to mention for UK credibility.
- Others: **Smartlinx**, **Symplr Workforce**.

**Industry advertises:** demand forecasting, self-service swaps, mobile
apps, credential/competency tracking, payroll integration, compliance
dashboards, fatigue scoring, open-shift marketplaces. **The
optimisation engine is rarely the headline feature.** UI, integrations,
and compliance reporting are.

**Implication:** our research positioning should be the *opposite* —
we differentiate on the optimisation engine + the validation rigour
(reproducibility, fairness audit, regulatory conformance). The Lab tab
is what makes us defensible in a peer-reviewed journal in a way that
none of the commercial tools attempt.

---

## 9. Validation-plan upgrades from this research

Concrete additions to fold into [`VALIDATION_PLAN.md`](VALIDATION_PLAN.md)
and [`RESEARCH_METRICS.md`](RESEARCH_METRICS.md):

1. **Adopt INRC-II as the headline benchmark**, with Curtois NRP
   collection as the breadth dataset and NSPLib for scaling sweeps.
2. **Add CV (coefficient of variation) of workload alongside Gini** as
   a fairness metric so we're cross-comparable with both econ-flavoured
   and OR-flavoured papers.
3. **Add INRC-II penalty score as a first-class output metric** when
   running on INRC-II instances. Implement the translator in
   `lib/objective_translator.py`.
4. **Add coverage shortfall and over-coverage as separate metrics**
   (currently rolled up into idle-weekday penalty).
5. **Include a regulatory-conformance test suite as a hard-constraint
   module** for at least one jurisdiction. Recommend UK NHS junior-
   doctor + WTD as the first one (covers EU + Commonwealth + UK
   audiences).
6. **Implement PuLP+CBC MILP baseline** alongside the greedy and
   random-repair baselines already planned.
7. **Use "Nurse Rostering Problem (NRP)" as the standard term** in all
   publication-facing materials, with a note that the formulation is
   generalised to physician rosters via tier labels.
8. **Add a one-page "H-rule → De Causmaecker / Vanden Berghe taxonomy"
   mapping table** to the publication and to `docs/CONSTRAINTS.md` so
   reviewers can immediately see we conform to standard categorisation.

These eight items are the most important upgrades from "internally
consistent" to "publication-ready and field-recognisable".
