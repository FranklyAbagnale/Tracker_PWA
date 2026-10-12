---
tags: [runbook, operations, security]
---

# Runbook — Rotate Token

Purpose: replace a GitHub write credential on schedule or after suspected
compromise.

Frequency: every 90 days, or immediately on suspicion.

## Procedure

### If using per-user PATs (Option A)
1. GitHub -> Settings -> Developer settings -> Personal access tokens ->
   Fine-grained tokens.
2. Generate a new token: one repository, Contents: Read and write, expiry
   90 days.
3. In the app on the affected device: Sign out (clears stored token).
4. Sign in and paste the new token.
5. Verify a test write succeeds.
6. Revoke the old token in GitHub.

### If using a proxy (Option B)
1. Generate a new PAT with the same scope.
2. Update the proxy secret:
   ~~~bash
   wrangler secret put GITHUB_TOKEN
   ~~~
3. Deploy the proxy.
4. Verify a test write through the app.
5. Revoke the old token.

## Verification
- [ ] Test write commits successfully.
- [ ] Old token returns 401 when used.
- [ ] No token value appears in any log, commit, or client bundle.

## Related
- Authentication and Secrets
- ADR-006 Token Storage and Proxy
- Security and Privacy
