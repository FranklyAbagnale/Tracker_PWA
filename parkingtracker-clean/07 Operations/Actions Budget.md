# Actions Budget

Goal: GitHub Actions minutes used must not depend on how many people use the
app. Assumption: the "200 minutes" limit is per month (GitHub's billing period).
If it is a different window, the math below still holds because usage is zero
for field activity.

## The rule
**Nothing the app does may start a workflow.** Each save is 3-4 commits
(photo, vehicle, plate, index). A workflow triggered by those would run
thousands of times with dozens of users. So:

| Workflow | Trigger | Started by app users? | Cost per run |
|---|---|---|---|
| `pages.yml` | push touching `web/**`, or manual | No (app never writes `web/`) | about 1 min, capped at 5 |
| `validate.yml` | pull request, or manual | No | about 2-3 min, capped at 5 |

Removed: `index.yml` (rebuilt the index on every data push). The app now
updates `data/index.json` itself in the same sync (`saveIndexEntry`). No
schedules anywhere.

## Worst case
Runs happen only when the owner changes code. Assume 20 deploys and 20 PR
validations in a month, each hitting the 5-minute cap:
20 x 5 + 20 x 5 = **200 minutes, the absolute ceiling**. Realistic use
(1 + 3 minutes per change, 10 changes) is about **40 minutes/month**. Cancelled
superseded runs (`cancel-in-progress`) cost less still. Users: 1 or 1,000, same number.

Minutes round up per job, so count each job as at least 1 minute.

## Enforcement
- `tests/test_workflows.py` fails if any workflow: has a `schedule` trigger or
  any event outside push / pull_request / workflow_dispatch; has a push trigger
  without `paths` or one matching `data/**` or `photos/**`; lacks
  `timeout-minutes` <= 10; uses a non-`ubuntu-latest` runner (Windows is 2x,
  macOS 10x); lacks `concurrency` with cancel-in-progress.
- Run it before merging any workflow change: `python3 -m unittest tests.test_workflows`.

## Account settings (one-time)
1. Settings -> Billing -> Budgets and alerts: spending limit **$0** so Actions
   stops rather than bills at the limit. Add usage alerts at 50% and 80%.
2. Do not enable CodeQL "default setup" or Dependabot version updates; both run
   on their own schedule and consume minutes.
3. Do not add third-party apps or integrations that run workflows.

## Habits that save minutes
- After a test session run `npm run validate` locally (free) instead of waiting
  for CI. It checks every record against the schemas.
- Batch web changes into one push; `pages.yml` runs per push.
- Use `workflow_dispatch` to re-run on demand rather than pushing empty commits.

## Not an Actions issue, but related
The shared token is subject to GitHub's secondary rate limit of about 500
content-generating requests per hour (80 per minute). Each save is 3-4 writes,
so the whole test group can do roughly 125-165 saves per hour combined. Failures
show as "rate limit" and stay queued on the phone, then retry. Plan sessions
so testers are not all saving at once.

`data/index.json` grows with the number of vehicles (about 250 bytes each).
Contents-API reads over 1 MB use a slower path, which is around 4,000 vehicles.
Revisit before that point.
