---
tags: [roadmap, moc]
---

# Roadmap

| Phase | Theme | Status |
|---|---|---|
| Phase 1 - MVP | Lookup, capture, GitHub write | Implemented; awaiting real-device test |
| Phase 2 - Offline and Nearby | PWA, outbox, proximity | Implemented; awaiting real-device test |
| Phase 3 - Hardening | Proxy, validation, polish | Partly done (CSP, escaping, schema, CI); proxy not started |

## Sequencing principle
Ship the smallest thing that is genuinely useful in the field, then harden.
Do not build the proxy before there is a second user. Do not build offline
support before the online path is proven.

## Cut lines
If time runs short, cut in this order:
1. Map view
2. Audit view
3. Push notifications
4. Thumbnails
5. Offline photo queuing (keep offline records)

Never cut: schema validation, conflict retry, or the pending-upload
indicator. Those are what keep the data trustworthy.

## Related
- Project Overview
- Open Questions
