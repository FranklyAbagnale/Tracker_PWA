---
tags: [architecture, security, privacy]
---

# Security and Privacy

## Threat model
Realistic threats, in order of likelihood:
1. Lost or shared device with a stored write token.
2. Token exfiltration from a public repository's client code.
3. Unwanted location tracking of field staff.
4. Data scraping of vehicle locations from a public repo.
5. Malicious write by a holder of a valid token.

## Controls

| Threat | Control |
|---|---|
| Lost device | Token expiry, per-user tokens, remote revocation |
| Token exfiltration | Serverless proxy; never a token in public code |
| Location tracking | Consent-gated capture, no background tracking |
| Scraping | Private repository if location is sensitive |
| Malicious write | Schema validation, rate limiting, revertible history |

## Location privacy rules
1. Capture only on explicit save. Never poll location in the background.
2. Never store a location for a user who declined.
3. Coarsen on export: round to ~3 decimal places (~100 m).
4. No location in URLs.
5. Disclose purpose. A one-line explanation improves grant rates.
6. Decide and document a retention period.

## Repository privacy
If the repository is public, remember:
- All data is world-readable and indexed.
- All history is permanent.
- Anyone can fork and retain a copy.

For a public repo, either omit precise location data, coarsen it at write
time, or keep location-bearing records in a separate private repository.

## Content Security Policy

~~~html
<meta http-equiv="Content-Security-Policy"
      content="default-src 'self';
               img-src 'self' data: blob: https://*.githubusercontent.com;
               connect-src 'self' https://api.github.com https://*.githubusercontent.com;
               script-src 'self'; style-src 'self' 'unsafe-inline';
               base-uri 'none'; form-action 'none'">
~~~

GitHub Pages cannot set response headers, so a meta CSP is the available
lever.
