---
tags:
  - adr
status: accepted
date: 2026-10-09
---

# ADR-006 — Token Storage and Proxy

## Status
Proposed. Needs a decision before any non-trusted user is granted access.

## Context
The app must write to GitHub. Anything shipped to the browser is readable.
A write-capable token in client code is therefore a public write token.

## Options considered

### Option 1 — Fine-grained PAT in localStorage
One token per user, scoped to one repository, contents: write, 90-day expiry.
- Pro: no infrastructure, works immediately, no additional account.
- Con: extractable from any device that has it. No server-side rate limiting.
  Revocation is manual.

### Option 2 — Serverless proxy
A small edge function holds the token server-side. The client posts a record;
the proxy validates it, enforces a rate limit, attaches the token, calls
GitHub, returns the commit SHA.
- Pro: token never reaches the client. Enables server-side schema validation
  and rate limiting. Single place to rotate credentials.
- Con: one more component. Needs its own account (Cloudflare Workers, Vercel,
  Deno Deploy all have sufficient free tiers). Introduces a network hop.

### Option 3 — GitHub OAuth / GitHub App
Users authenticate with GitHub; writes attributed to their account.
- Pro: best audit trail. No shared secret.
- Con: every field user needs a GitHub account. OAuth flow on mobile PWA is
  awkward. Overkill.

## Recommendation
Adopt Option 2 when any of these becomes true:
- The repository is public.
- Any user is not fully trusted.
- Rate limiting or server-side validation is wanted.

Until then, Option 1 is acceptable for a small trusted group on a private
repository, with the mitigations in Authentication and Secrets.

## Decision
Option 1

## Revisit triggers
- Repository visibility change.
- Addition of a user outside the trusted group.
- Any suspected token compromise.

## Related
- Authentication and Secrets
- Security and Privacy
