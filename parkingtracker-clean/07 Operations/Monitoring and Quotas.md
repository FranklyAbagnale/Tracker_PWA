---
tags: [operations, monitoring]
---

# Monitoring and Quotas

## What to watch

| Metric | Limit | Check | Action if approaching |
|---|---|---|---|
| Actions minutes | 2,000/mo (private free tier) | Repo Settings Billing | Remove or restrict workflows |
| API requests | 5,000/hr authenticated | Response headers | Add caching, batch writes |
| Pages bandwidth | 100 GB/mo soft | Repo Insights Traffic | Reduce photo sizes |
| Repo size | 1 GB soft | du -sh .git | Move photos to object storage |
| Record count | ~10,000 practical | ls data/plates | wc -l | Consider sharding |
| Index size | ~500 KB | ls -lh data/index.json | Split index by region |

## Monthly checklist
- [ ] Check Actions minutes usage. Expected: 0.
- [ ] Check repository size and photos/ growth.
- [ ] Check data/index.json size against the 500 KB budget.
- [ ] Check for orphaned photos (no referencing record).
- [ ] Check for orphaned records (no index.json entry).
- [ ] Confirm token expiry dates.
- [ ] Review open questions in Open Questions.

## Useful commands
~~~bash
du -sh .git
du -sh photos/ && ls photos/ | wc -l
ls data/plates/*.json | wc -l
ls -lh data/index.json
python scripts/validate_records.py --check-index
python scripts/validate_records.py --check-photos
~~~

## Alerts worth setting up
- GitHub notification on failed workflow runs (should be rare, PRs only).
- A calendar reminder for token rotation every 90 days.
- A calendar reminder for the monthly checklist above.

## Related
- ADR-005 Local Transformations over Actions
- Performance and Caching
