---
tags: [architecture, pwa, offline]
---

# PWA and Offline

## What makes it a PWA
Two files, plus HTTPS:
1. manifest.json — name, icons, display: "standalone", theme colours.
2. Service worker — intercepts fetches, caches the app shell.

## Install behaviour
iOS Safari: Share -> Add to Home Screen. No automatic prompt. You must tell
users to do this.

Android Chrome: Chrome offers an install prompt automatically once the
manifest and service worker criteria are met.

## Caching strategy

| Content | Strategy | Why |
|---|---|---|
| App shell | Cache-first, update in background | Instant load |
| data/index.json | Stale-while-revalidate, 5 min TTL | Fast, tolerant |
| data/plates/*.json | Network-first, cache fallback | Fresh when possible |
| photos/* | Cache-first, LRU, cap ~50 MB | Expensive to refetch |
| GitHub API writes | Never cached | Must always hit network |

## Offline writes — the outbox pattern
1. Serialise the intended write with a UUID and timestamp.
2. Store it in IndexedDB.
3. Apply optimistically to the local index.
4. Mark the affected plate pending: true in the UI.
5. On online event or app foreground, flush in FIFO order.
6. On success, clear the outbox entry and pending marker.
7. On repeated failure, keep it queued and surface a Pending uploads list.

Never discard a queued write. If truly unmergeable, keep it and ask the user.

## Testing offline
Chrome DevTools -> Network -> Offline. On a real device, airplane mode.
Always test app restart while offline. That is where naive implementations
lose data.
