---
tags: [operations, deployment]
---

# Deployment Guide

## One-time setup
1. Create the repo (or use the existing one) and push this tree to `main`.
2. **Settings -> Pages -> Build and deployment -> Source: GitHub Actions.**
3. Confirm `.github/workflows/pages.yml` ran (Actions tab). The app URL is
   `https://<owner>.github.io/<repo>/`.
4. If the repo owner or name differs from `FranklyAbagnale/ParkingTracker`,
   edit `REPO_OWNER` / `REPO_NAME` in `web/js/config.js`.
5. **Settings -> Actions -> General -> Workflow permissions:** allow
   *Read and write permissions*.

## What deploys
Only `web/` is published. `data/`, `photos/` and the vault notes are not served
by Pages; the app reads and writes them through the GitHub API.

| Workflow | Trigger | Does |
|---|---|---|
| `pages.yml` | push to `main` touching `web/` | publishes the app |
| `validate.yml` | pull request; manual | schema validation + tests |

No workflow runs on data or photo pushes (see `Actions Budget.md`). The app
updates `data/index.json` itself.

## Local development
```bash
npm run serve            # http://localhost:8080
```
`localhost` is treated as a secure context, so camera, geolocation and the
service worker work. `file://` does not (ES modules are blocked).

## Releasing a change
The service worker is network-first, so a deploy reaches users on their next
online load. If you change the cached file list in `web/service-worker.js`,
bump `CACHE_NAME`.

## Phone testing checklist
Use `09 Testing/Manual Test Checklist.md` on a real iPhone (Safari) and a real
Android phone (Chrome). The automated smoke test (`tests/e2e_smoke.py`) uses a
fake camera and a fake GitHub, so it cannot replace this.

## Related
- Authentication and Secrets
- Runbook - Rotate Token
- ADR-009 Hosting and Automation Changes
