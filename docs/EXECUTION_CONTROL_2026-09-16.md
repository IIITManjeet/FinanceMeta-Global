# FinanceMeta — Execution Control (2026-09-16)

## Operating truth

FinanceMeta currently has two distinct surfaces:

- `FinanceMeta-Global`: programs, cohorts, partnerships, operating packets and pre-result research contracts.
- `finance4all-global-reach`: member-facing product/auth/RLS/portal and production evidence.

Do not mix product-release blockers with cohort/program blockers.

## Product P0

Canonical Finance4All main is currently repository/release healthy. The remaining product gates are credentialed evidence, not another source rewrite:

1. verify email/password signup, login, logout and password recovery;
2. verify Google OAuth end to end;
3. verify onboarding and member portal access;
4. prove user A cannot read/write user B data;
5. prove unauthenticated and cross-account RLS fail closed;
6. verify admin/role boundaries;
7. reconcile canonical Supabase migration provenance through authorized read-only access and supported migration-repair tooling;
8. do not substitute another Supabase project or infer production migration history from local replay.

## Program P0

### FinTech Studio 01
Do not call it launched until:

- at least two builders explicitly accept one bounded 7-day scope;
- one reviewer accepts the evidence rubric;
- every builder freezes `brief.md` before implementation;
- submission/review window is fixed;
- the first prototypes have runnable code, tests, machine-readable evidence and `findings.md`.

Recommended first-cycle lanes: financial-data utility, consumer-finance education/decision support, or research-workflow tooling. No live trading or personalized investment advice.

### Quant Research Cohort 01
Do not unlock held-out evaluation until:

- research owner accepts;
- data/integrity owner accepts;
- independent reproducibility reviewer accepts;
- raw-data integrity lock is complete;
- train/validation-only implementation reproduces;
- selected configuration and source SHA are frozen;
- reviewer signs held-out unlock.

A negative or null out-of-sample result remains a valid cohort result.

## Applicant routing

One applicant should have one primary current route. Use:

- `QUANT_RESEARCH`
- `FINTECH_STUDIO`
- `FOUNDATIONS`
- `RESEARCH_WRITING`
- `COMMUNITY_PROGRAMS`
- `HOLD`

For every serious applicant store/record:

- route;
- named owner/reviewer;
- first bounded artifact;
- due date;
- evidence location;
- current state: `INVITED`, `ACCEPTED`, `ACTIVE`, `REVIEW`, `COMPLETE`, `BLOCKED`, `STOPPED`.

Do not count form completion as activation.

## Member progression

Canonical progression:

`Applicant -> bounded trial -> reviewed artifact -> contributor -> project owner/researcher/builder -> reviewer/lead`

Progression is earned by evidence and ownership, not by tenure or title.

## External-proof queue

Prioritize closure of existing external signals before new outreach:

1. FMP management approval / no-go + exact event terms.
2. Existing buildathon sponsor-use evidence.
3. HAVEN deliverable/decision record where still active.
4. One standards-quality educational resource submission.
5. Real user/reviewer evidence from the first FinTech Studio prototypes.

Warm replies and proposed API terms are not delivered partnerships.

## Metrics

Weekly operating metrics:

- qualified visits;
- completed applications;
- trial-worthy applicants;
- invitations sent;
- explicit acceptances;
- active bounded trials;
- reviewable artifacts completed;
- independent reproductions/reviews;
- prototype continuations;
- cohort completion;
- delivered partner/sponsor outcomes.

## Kill / merge rules

Pause a lane if it has no owner or no reviewable artifact for two review cycles. Merge duplicated programs rather than keeping multiple labels alive. Stop broad recruiting when reviewer capacity becomes the bottleneck.

## Immediate order

1. Close product credentialed auth/RLS evidence and migration provenance when authorized access exists.
2. Integrate/review the current facilitator + FinTech Studio operational packet stack in normal review order.
3. Staff FinTech Studio with two builders + one reviewer.
4. Staff Quant Cohort with all three required roles.
5. Freeze each accepted participant's first artifact and deadline.
6. Convert current partnership threads into explicit yes/no/delivered states.
7. Report outputs and completions separately from community/application counts.
