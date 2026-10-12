---
tags: [roadmap, audit, stabilization, security, testing]
status: approved-for-planning
created: 2026-10-12
baseline_branch: main
owner: project-maintainer
---

# Tracker PWA — Stabilization and Improvement Plan

**Date:** 2026-10-12  
**Repository:** [FranklyAbagnale/Tracker_PWA](https://github.com/FranklyAbagnale/Tracker_PWA)  
**Plan status:** Planning baseline; tasks are **not** complete merely because they are described here.  
**Working method:** Small, independently reviewable changes; preserve existing functionality; record test evidence and commit SHAs.

## 1. Purpose and current baseline

Tracker_PWA is a photo-first, offline-capable PWA for vehicle/plate/sighting records. Implemented code and documentation describe camera/photo capture, vehicle and plate lookup, geographical and descriptive search, IndexedDB outbox, GitHub Contents API storage, optional California plate lookup through a proxy, sample data tools, validators, import tools, and GitHub Pages deployment.

This is **code/documentation inspection**, not proof of passing tests or successful phone deployments. As of this plan, there is **no recorded executed test baseline** in this assessment. Treat the application as a *controlled beta for synthetic data*, **not approved for real sensitive data**.

### Confirmed strengths
- Modular vanilla-JS PWA, no framework or build dependency.
- JSON schema and tooling for records, validation and XML/CSV import.
- IndexedDB-backed queued writes, conflict retry and explicit failed/conflict states.
- Node/Python/browser test suites and low-cost Actions policy.
- Detailed operations documentation and architecture decisions.

### Confirmed/likely gaps to resolve
- Browser `localStorage` holds a GitHub write token; shared-token field testing is documented. A write token to the repo may also change application source. **P0 security issue**.
- Repository is public; photos, sightings, locations, timestamps, notes, and flags must remain synthetic. Making an exposed repository private later does not retract copies or history.
- Saving photos, vehicle, plate, and index requires distinct API writes; partial completion, retry and inconsistent projections need formal validation.
- `data/index.json` is one shared write target, creating contention under parallel use.
- `validate.yml` runs Node/Python tests and schemas but not Chromium e2e tests; real iOS and Android acceptance evidence is not recorded here.
- Service-worker cache name is updated manually.
- Documentation includes legacy `ParkingTracker` repository/path references (e.g. root README deployment URL), and ADR-006 says both `accepted` in YAML and `Proposed` in the body.
- Plate-state definitions are manually duplicated in multiple languages/tools.

## 2. Rules for execution

1. **Safety and privacy:** Do not enter or migrate real identifiable vehicle or location data while access controls remain unresolved. Use fake vehicles/photos with nonidentifying coordinates. Never paste secrets into issues, logs or markdown.
2. **Source of truth:** `main` holds approved plans and releases. Make application changes in short-lived branches with PRs, except for explicitly requested documentation commits such as this one.
3. **Work unit:** Prefer one focused change per pass; provide evidence, blockers and a clean next-step handoff after each pass. Target passes <= 10 minutes; split further if necessary.
4. **Verification:** Do not mark a step complete from code existence alone. Record command, result, environment/date, affected commit and any failed cases.
5. **Compatibility:** Preserve existing data format until a migration is explicitly designed and tested. Never silently alter persisted records.
6. **Actions cost:** Keep field data/photo writes from triggering workflows. Evaluate any CI changes against the documented Actions budget.
7. **Tracking:** For every step set Status = Not started / In progress / Blocked / Verified, with owner, PR/commit and evidence link. Use linked issues as implementation tracking if useful.
8. **Change control:** For privacy, auth, retention, identity and flag semantics, document the decision before implementation. Avoid silently inferring legal or policy authority to collect data.

## 3. Priorities and release gates

| Gate | Criteria | Blocks |
|---|---|---|
| **G0 — Safe testing** | Fake data only; token scope and revocation confirmed; Pages and public-history exposure understood | Any field test |
| **G1 — Reproducible baseline** | Unit/Python/schema/e2e results recorded; smoke-tested on real iOS and Android; defects triaged | Broader beta |
| **G2 — Authorized private operation** | Individually accountable users, private data and photos, server-side authorization/validation/rate limiting, documented retention/deletion | Real data |
| **G3 — Durable writes** | Interrupted and concurrent saves have tested no-loss behavior; reconciliation reports clean | Wider rollout |
| **G4 — Maintainable release** | Automation, release/version discipline, traceable tests and operations handoff | Routine ongoing operation |

**Definition of Done for every task:** Artifact committed; tests appropriate to the change pass (or exceptions documented); documentation updated; verification evidence recorded; reviewer acceptance obtained.

## 4. Ordered implementation steps

### Phase A — Inventory, test baseline and documentation (P0; G0/G1)

#### 01 — Snapshot repository and current environment
**Action:** Record `main` SHA, default branch, repository visibility, Pages URL, branch protections, workflow names, and open defects/PRs. Inventory `web/`, `api/`, `data/`, `schema/`, `scripts/`, `tools/`, `tests/`, `.github/` and the Obsidian documentation folders. Do not copy secrets or user records into the report.  
**Output:** `09 Testing/Baseline - Repository Inventory.md` or equivalent.  
**Verify:** Every top-level subsystem accounted for; snapshot cites commit SHA.

#### 02 — Feature-to-code-to-test traceability matrix
**Action:** List core user journeys: sign-in, take photo, create/update vehicle, normal/unknown/near-match plate search, local/description search, previous sightings, editing, sync, retries, imports, optional lookups and log-out. Map each to source module, schema field, automated test and manual test.  
**Output:** `09 Testing/Feature Verification Matrix.md`.  
**Verify:** Each feature has evidence or is explicitly marked unverified/not implemented.

#### 03 — Run static validation and script tests
**Action:** In clean environment run `npm test`, `npm run test:py`, `npm run validate`, `npm run build-index` (check for unintended index diff) and record installed runtimes and versions. Avoid committing generated data until inspected.  
**Output:** Dated test log with pass/fail totals and failures.  
**Verify:** Reproducible results tied to a commit SHA.

#### 04 — Run browser and tooling end-to-end tests
**Action:** Install documented Playwright prerequisites; run `npm run test:e2e`, then individually run XML/CSV tooling e2e suites documented in `tests/README.md`. Use fake data and isolated working directory.  
**Output:** Browser test report and defect issues.  
**Verify:** Capture actual outputs; no claim of success without execution.

#### 05 — Real mobile acceptance and offline recovery
**Action:** Execute `09 Testing/Manual Test Checklist.md` on named versions of iPhone Safari/PWA and Android Chrome/PWA. Test install, permissions, photo capture/compression, airplane mode, app restart, reconnect, conflict and full storage conditions.  
**Output:** Device/test build matrix with recorded results and screenshots where non-sensitive.  
**Verify:** Critical field journeys pass on **both** platforms; unresolved issues explicitly triaged.

#### 06 — Documentation truth audit
**Action:** Cross-check root README, `web/README.md`, `data/README.md`, schemas, deployment guide, tester instructions, runbooks, architecture decisions, and tests against current files. Correct stale `ParkingTracker` / `Tracker_PWA` names and deployed URL; keep product branding deliberate.  
**Output:** Reviewed documentation diff and a change log.  
**Verify:** Quick-start instructions work from a clean checkout.

#### 07 — Resolve requirements and ADR status
**Action:** Reconcile ADR-006 YAML `accepted` with in-body `Proposed`; review other ADR statuses. Translate project success criteria (lookup <2 s on 4G, capture <30 s, two-user no-loss writes, minimal Actions use) into measurable tests and thresholds.  
**Output:** Decision register and requirement/verification matrix.  
**Verify:** Each release-critical requirement has owner, metric and planned evidence.

### Phase B — Privacy, authentication and authorization (P0; G2)

#### 08 — Threat model and sensitive-data inventory
**Action:** Document assets (tokens, vehicle/plate identities, geolocation, photos, user names, audit trails), threat actors, abuse cases, retention, data-subject correction/deletion needs, and risks of public Git history. Assess implications of vehicle flags and user-generated accusations; review naming and purpose of flag vocabulary with product owner.  
**Output:** Threat model, data classification and an approved safe-data handling policy.  
**Verify:** Explicit threat-to-control mapping, with non-goals recorded.

#### 09 — Split application and private records
**Action:** Design and implement a public app deployment with independent, access-restricted data and photo storage. Establish migration and rollback plan, including backups, history exposure review, token revocation and URL/config changes. Do not assume turning a repo private undoes prior publication.  
**Output:** Architecture decision, migration runbook, tested configuration.  
**Verify:** Anonymous user cannot read private records or photos; app still deploys.

#### 10 — Design individual authentication
**Action:** Select identity mechanism (e.g. hosted auth or per-user OAuth) appropriate for mobile PWA. Avoid one shared privileged PAT; require authenticated identity independent of a self-entered observer name. Specify session expiry, revocation and logout.  
**Output:** Approved auth ADR and acceptance tests.  
**Verify:** Distinct users can be audited; stolen/revoked sessions cannot write.

#### 11 — Implement server-side write API
**Action:** Move write credentials to server-side infrastructure. Validate request payload against versioned schemas, authorize record/photo access, enforce size/rate limits, CSRF/origin and replay defenses appropriate to chosen auth, and minimize logged personal data. Keep the client outbox contract stable through an adapter.  
**Output:** Secure API and migrated client transport.  
**Verify:** Anonymous/unauthorized/invalid/rate-limited writes denied; no write token shipped to client.

#### 12 — Permissions, audit and lifecycle
**Action:** Define reader/field-user/reviewer/admin capabilities, immutable audit metadata, session revocation, backup restore and retention/deletion policies for records and photos. Separate operational logs from public source history.  
**Output:** Authorization matrix and operations runbooks.  
**Verify:** Automated tests exercise every role and record scope; deletion workflow reviewed.

### Phase C — Synchronization, correctness and storage (P1; G3)

#### 13 — Document mutation contract and invariants
**Action:** Define unique operation IDs, record versions, expected ordering, duplicate/replayed update handling and invariants: photo references exist, plate pointers resolve, index agrees with vehicle state, timestamps are monotonic where required.  
**Output:** Sync protocol/consistency specification.  
**Verify:** Every failure point and recovery behavior documented.

#### 14 — Harden durable outbox and retry logic
**Action:** Add idempotent operations; persist per-stage progress or support safe whole-operation replay. Include transient error backoff and explicit error classes. Review IndexedDB write/read failures and quota exhaustion.  
**Output:** Updated sync implementation and fault-injection tests.  
**Verify:** App restart, connection loss, repeat submit and partial upload create no duplicate sightings/lost photos.

#### 15 — Concurrent save stress tests
**Action:** Exercise two users editing same/different records, same plates, index collisions, 409/422 conflicts and out-of-order arrival. Stress shared `data/index.json` and record latency, retries and data loss.  
**Output:** Test harness/results, performance and retry metrics.  
**Verify:** Defined concurrent-use target passes without silent lost writes.

#### 16 — Reconciliation and repair tooling
**Action:** Build **read-only audit first**, checking plate-to-vehicle pointers, photo paths, sighting references, index equivalence and malformed JSON; then implement explicit, reversible repair mode with dry-run, backup and review.  
**Output:** `scripts/` audit/repair utilities and runbook.  
**Verify:** Seeded broken datasets are detected, dry-run changes nothing, approved repair restores consistency.

#### 17 — Decide future storage/search path
**Action:** Compare continued GitHub-backed storage behind API, partitioned index and transactional database/object storage for likely record count, photo volume, write contention, cost and privacy. Keep migration behind existing transport/interface boundaries.  
**Output:** Decision matrix and migration trigger thresholds.  
**Verify:** Benchmarks support choice; rollback and export format documented.

### Phase D — Product quality and maintenance (P2; G4)

#### 18 — Explain sync state in the UI
**Action:** Show pending/failed/conflicted/synced states and last-success timestamp; provide safe Retry and diagnostic copy (without tokens or sensitive data). Warn clearly before clearing local data or logout while unsynced.  
**Output:** UI refinement and acceptance tests.  
**Verify:** Nontechnical tester can distinguish locally saved from server-confirmed data.

#### 19 — Protect in-progress capture and form edits
**Action:** Preserve unsaved vehicle/form state across camera navigation and interruptions, with deliberate discard affordance and storage limits. Verify on iOS home-screen mode and Android.  
**Output:** Form recovery tests and updated tester guide.  
**Verify:** No silent loss on navigation, camera return or app backgrounding.

#### 20 — Unify schema and state vocabularies
**Action:** Choose a machine-readable source for plate states and other repeated enums; generate JavaScript/Python/tool definitions or enforce exact fixtures in CI. Version schemas and publish migrations for incompatible changes.  
**Output:** Shared definitions, code generation/check and migration policy.  
**Verify:** Intentional schema changes fail fast when consumers are not updated.

#### 21 — Automate offline cache/release identification
**Action:** Generate/cache-bust service-worker assets on release (or test a deterministic manifest); display app version/build SHA; preserve network-first behavior and predictable rollback.  
**Output:** Release/build automation and cache invalidation tests.  
**Verify:** Devices receive intended version after update, and offline fallback still works.

#### 22 — Observability, quality and accessibility
**Action:** Add privacy-safe metrics for queue age, retries, failed writes, request latency, storage limits, import errors and app version. Audit touch targets, contrast, focus/keyboard, screen-reader labels and reduced-motion behavior.  
**Output:** Operations dashboard/report plan and accessibility defects.  
**Verify:** Failures can be diagnosed without exposing user records or tokens.

#### 23 — Test and deployment gate improvements
**Action:** Define minimum checks for PRs and release tags; add browser e2e where budget allows (or a mandatory documented manual run when not). Review branch protections, least-privilege workflows, pinned dependencies, environments and release rollback. Preserve no-workflow-on-field-writes rule.  
**Output:** Release checklist and CI policy.  
**Verify:** Bad schemas/core regressions block a merge; Actions costs remain controlled.

#### 24 — Onboarding, support and maintainers' runbooks
**Action:** Produce one current Quick Start; user guide; safe test-data instructions; deployment/auth setup; incident/secret rotation; backup/restore; partial-sync repair; migration and release notes. Link from root README/Obsidian home without duplicating instructions.  
**Output:** Cohesive operations index and verified walkthrough.  
**Verify:** A new maintainer can deploy a test instance, run tests and recover a seeded failure unaided.

#### 25 — Pilot, measure and release decision
**Action:** Conduct a limited, authorized pilot **only after G2 and G3** with preapproved non-sensitive or properly governed data; measure capture time, plate lookup latency, queue failure rate, conflict recovery and support load. Decide go/no-go against documented requirements.  
**Output:** Dated release-readiness report, known limitations, prioritized post-pilot backlog.  
**Verify:** Owner signs off G0–G4 with links to evidence, not assumptions.

## 5. Work sequencing and parallelism

- **Immediate safe parallel work:** 01–07 can proceed without production-data migration. 08 may start alongside these but must finish before architecture decisions.
- **Critical dependency:** 08 → 09/10 → 11 → 12; do not treat an isolated proxy as complete security without identity, permissions and private storage.
- **Integrity dependency:** 13 → 14 → 15 → 16; 17 uses findings from 15 and capacity measurements.
- **Later work:** 18–24 may be developed independently after interfaces are stabilized; 25 requires the gates.
- **Avoid:** Large feature additions, database rewrite, or cosmetic UI redesign before measured safety/integrity defects are understood.

## 6. Standard step execution record

Copy this record into an issue or dated note for each step:

```md
### Step XX — Name
Status: Not started | In progress | Blocked | Verified
Owner:
Baseline main SHA:
Branch / PR / commit:
Scope (files):
What changed:
Commands/tests run (versions, outcomes):
Acceptance criteria result:
Known risks/defects:
Rollback/backup instructions:
Next atomic task:
```

## 7. Initial next action

**Start Step 01** by capturing the current `main` SHA and enumerating source/docs/tests/workflows; then Step 02 before modifying application behavior. After each small work pass, commit or save a durable note and state the exact next task.

## 8. Source references inspected for this plan

- `README.md`, `package.json`, `00 Home/Project Overview.md`
- `web/README.md`, `web/js/config.js`, `web/js/github.js`, `web/js/sync-manager.js`, `web/js/storage.js`, `web/js/index-manager.js`, `web/service-worker.js`, `web/index.html`
- `data/README.md`, `schema/README.md`, `api/README.md`, `tests/README.md`
- `.github/workflows/validate.yml`, `.github/workflows/pages.yml`, `.github/README.md`
- `07 Operations/Deployment Guide.md`, `07 Operations/Runbook - Shared Test Token.md`, `07 Operations/Actions Budget.md`
- `04 Decisions/ADR-006 Token Storage and Proxy.md`, `09 Testing/Manual Test Checklist.md`

**Important:** Findings are based on available repository text. Workflow runs, phone acceptance, deployed site operation and security behavior require independent execution and verification.
