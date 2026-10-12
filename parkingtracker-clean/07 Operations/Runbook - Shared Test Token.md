---
tags: [operations, runbook, security]
---

# Runbook: Shared Test Token

One fine-grained token, handed to a small group of trusted testers. This is
ADR-006 Option 1 stretched to several people, which is acceptable for a
time-boxed test and not for anything longer. Read **Risks** first.

## Risks (what sharing one token means)
1. **Anyone holding it can write to the repo.** Every commit is authored by the
   token owner, so git history cannot tell testers apart. The name each person
   enters at sign-in is stamped on their sightings (`observer`); that is the
   audit trail. `python3 scripts/audit_observers.py` summarises it.
2. **A write to `web/` is a write to the app.** The token can change the
   JavaScript that every tester then runs, and that code can read their stored
   token. Mitigation: require your approval before Pages publishes (below).
3. **The repo is public.** Everything testers save, photos included, is
   world-readable and permanent in git history, including after the repo goes
   private (anyone may already have cloned or forked it).
4. **A leak means rotating for everyone.**

## Create the token
Sign in to GitHub as the account that **owns the repo** (a fine-grained token can
only reach repos owned by its own resource owner; collaborators cannot create
one for someone else's personal repo).

1. <https://github.com/settings/personal-access-tokens/new>
2. Name: `parkingtracker-testers`
3. Expiration: **30 days** (shorter than the 90 days ADR-006 allows, because it is shared)
4. Resource owner: the account that owns the repo
5. Repository access: **Only select repositories** -> ParkingTracker
6. Repository permissions: **Contents: Read and write**. Leave everything else
   (Workflows, Actions, Pages, Administration...) at *No access*. Without
   *Workflows* the token cannot edit `.github/workflows/`.
7. Generate, copy it once.
8. Verify: sign in yourself, save a test vehicle, confirm the commit appears.

## Hand it out
- Send the token through a password manager share, Signal, or in person. Not
  email, not SMS, not a group chat.
- Send the app URL and `09 Testing/Tester Guide.md` separately.
- Tell each person to use their own name at sign-in.
- Keep a list of who has it, so you know whom to tell on rotation.

## Require approval before the app is published
This is what stops a misused token from changing the app everyone runs.

1. Repo **Settings -> Environments -> github-pages**
2. **Required reviewers:** add yourself
3. **Deployment branches and tags:** selected branches -> `main`

`pages.yml` only runs when `web/` changes. Data writes from the app never touch
`web/`, so testers will not trigger it. When it does run, GitHub emails you to
approve; if you did not make that change, deny it and check the commit.

## Watch activity
```bash
git pull
python3 scripts/audit_observers.py              # one line per person
python3 scripts/audit_observers.py --who Sam    # everything Sam wrote
git log --since="1 day ago" --stat -- web .github   # should be empty unless you changed the app
```
`(unattributed)` is sample data or a record from before names were added.

## Undo a bad write
- One record: `git revert <commit>` (each save is its own commit).
- A person's whole contribution: list it with `--who`, then `git rm` those
  records or photos and run `python3 scripts/build_index.py`.
- See also *Runbook - Recover from Bad Commit*.

## Rotate or revoke (leak, a tester leaves, or end of test)
1. GitHub -> Settings -> Developer settings -> Fine-grained tokens -> delete it
   (or Regenerate to keep the same settings).
2. Every tester's next sync fails with "Token rejected". Unsynced work stays
   queued on their phone.
3. For rotation: create the new token, send it out, testers tap **Log out** and
   sign in again. Queued items upload after sign-in.

## End of the test
1. Revoke the token.
2. Remove test data: `python3 scripts/generate_sample_data.py --clean`, then
   `git rm` the testers' records and photos, then `python3 scripts/build_index.py`.
3. **Make the repository private BEFORE any real data is entered.** Doing it
   afterwards leaves the real data public and in history for the whole window.
4. Check hosting first. Pages from a private repo needs a paid GitHub plan, and
   the published site is public regardless. Either upgrade, or keep a public
   *app-only* repo and point `REPO_OWNER` / `REPO_NAME` in `web/js/config.js` at a
   private *data* repo (a cleaner arrangement: the token then cannot touch app code).
5. Set `BANNER_TEXT = ''` in `web/js/config.js`, and consider `COARSEN_DECIMALS = null`
   if you want full-precision locations in the private repo.
6. Before more than a handful of people use it, build the serverless proxy (ADR-006 Option 2).

## Related
- ADR-006 Token Storage and Proxy
- Runbook - Rotate Token
- Security and Privacy

## Actions minutes and rate limits
The app never starts a workflow, so testers cannot use up Actions minutes
(`Actions Budget.md`). The shared token does share GitHub's secondary rate
limit (about 500 writes/hour; each save is 3-4 writes). If testers see "rate
limit" messages, saves stay queued and retry; ask them to pause for a few minutes.
After a session: `git pull && npm run validate`.
