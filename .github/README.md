# .github/ — workflows

Both workflows are deliberately cheap. Data and photo commits from the field app must never start a run (`tests/test_workflows.py` enforces this).

| Workflow | Runs when | Does |
|---|---|---|
| `workflows/pages.yml` | Push to `main` that changes `web/**` | Publishes `web/` to GitHub Pages |
| `workflows/validate.yml` | Pull requests, or by hand | Validates records and runs the tests |

Validate data locally instead (`npm run validate`); see `07 Operations/Actions Budget.md`.
