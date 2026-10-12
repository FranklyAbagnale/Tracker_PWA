---
tags: [architecture]
---

# Architecture Overview

~~~
iPhone Safari / Android Chrome
  -> PWA (index.html + js + sw)
  -> GitHub Pages (reads)  +  GitHub REST API (writes)
  -> GitHub Repository (data/plates/*.json, data/index.json, photos/)
  <- Data owner's machine (local scripts, git push)
~~~

## Layers
1. Presentation — mobile-first HTML/CSS, vanilla JS modules.
2. Client data — in-memory index, IndexedDB outbox, service worker shell.
3. Transport — fetch against Pages (reads) and REST API (writes).
4. Storage — the Git repository. Every write is a commit.
5. Offline tooling — local Python scripts, run by the data owner.

## Known weaknesses
| Weakness | Mitigation |
|---|---|
| GitHub API is not a database | Per-record files, retry on 409, index for reads |
| Write latency | Optimistic UI, outbox |
| Token exposure | Proxy or fine-grained PAT |
| Repo growth from photos | Client-side downscale, size budget |
