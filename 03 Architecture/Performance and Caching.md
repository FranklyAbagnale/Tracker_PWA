---
tags: [architecture, performance]
---

# Performance and Caching

## Budgets

| Operation | Target |
|---|---|
| Cold app load (uncached) | < 4 s on 4G |
| Warm app load | < 1 s |
| Plate lookup (index hit) | < 2 s |
| Nearby query (warm index) | < 3 s |
| Field capture save | < 1.5 s round trip |

## The index is the whole game
Without data/index.json, a nearby query would require fetching every record.
At 1,000 plates that is 1,000 requests, categorically impossible.

At 1,000 records with five short fields, the index is roughly 100-150 KB.
One fetch, cached aggressively, answers every list question.

Budget check: if index.json exceeds ~500 KB, add a build step that splits it.

## Client-side caching layers
1. Service worker Cache Storage — app shell, photos, index.
2. In-memory index — parsed once per session, mutated optimistically.
3. IndexedDB — outbox, photo blobs, last-known index snapshot.

## Reducing write cost
A PUT requires a preceding GET for the SHA. That is two round trips minimum.
- Cache the SHA for plates touched this session.
- Skip the GET entirely for new plates (omit sha from PUT).
- Batch offline writes sequentially rather than parallel.

## Measuring

~~~js
performance.mark('lookup-start');
// ... work ...
performance.mark('lookup-end');
performance.measure('lookup', 'lookup-start', 'lookup-end');
~~~

On real iOS devices, use Safari Web Inspector over USB.
