---
tags: [architecture, security]
---

# Authentication and Secrets

The central problem: the app must write to GitHub, but anything shipped to
the browser is readable by anyone who opens devtools.

## Options

### Option A — PAT in the client (phase 1 only)
A fine-grained PAT scoped to one repo with contents: write, entered once and
stored in localStorage.
- Pro: zero infrastructure, works today.
- Con: anyone who extracts the token can write. Only acceptable if every
  user is trusted and the repo is private.

### Option B — Serverless proxy (recommended)
A tiny function (Cloudflare Worker, Vercel Edge Function) holds the token
server-side. The client sends the record; the proxy attaches the credential.
- Pro: token never reaches the browser. Enables rate limiting and
  server-side validation.
- Con: one more component. Still free at this scale.

### Option C — GitHub OAuth / GitHub App
Users authenticate with their own GitHub account. Best audit trail. Highest
setup cost, awkward on mobile.

## Recommendation
Start with Option A for a small trusted group on a private repository. Move
to Option B when the repository becomes public, any user is not fully
trusted, or rate limiting is wanted.

## Token hygiene
- Fine-grained PAT, one repo, contents: write only, 90-day expiry.
- Stored in localStorage under a namespaced key.
- Cleared by a Sign out control.
- Never logged. Never in error reports.
- Rotated on schedule and immediately on suspicion.
