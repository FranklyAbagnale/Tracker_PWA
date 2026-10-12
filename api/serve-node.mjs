#!/usr/bin/env node
/**
 * Runs the lookup proxy as a plain Node service (Node 18+), for an internal host instead of Cloudflare.
 *
 *   PROVIDER=stub PROVIDER_KEY=... PORT=8787 node api/serve-node.mjs
 *
 * Reads the same settings as the Worker from process.env (see lookup.js). Phones must be able to reach this
 * host, so "internal" means a VPN, tunnel or reverse proxy with HTTPS; the app is served over HTTPS and
 * browsers refuse plain-http calls from it.
 */

import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { handleLookup } from './lookup.js';

const MAX_BODY_BYTES = 4096;

export function createNodeServer(env = process.env, deps = {}) {
  return http.createServer(async (req, res) => {
    try {
      const chunks = [];
      let size = 0;
      for await (const chunk of req) {
        size += chunk.length;
        if (size > MAX_BODY_BYTES) { res.writeHead(413).end(); return; }
        chunks.push(chunk);
      }
      const headers = new Headers();
      for (const [name, value] of Object.entries(req.headers)) if (typeof value === 'string') headers.set(name, value);
      const request = new Request(`http://${req.headers.host || 'localhost'}${req.url}`, {
        method: req.method,
        headers,
        body: ['GET', 'HEAD'].includes(req.method) ? undefined : Buffer.concat(chunks)
      });
      const response = await handleLookup(request, env, deps);
      res.writeHead(response.status, Object.fromEntries(response.headers));
      res.end(Buffer.from(await response.arrayBuffer()));
    } catch {
      res.writeHead(500, { 'content-type': 'application/json' }).end('{"status":"error","message":"Server error"}');
    }
  });
}

if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  const port = Number(process.env.PORT) || 8787;
  createNodeServer().listen(port, () => console.log(`parkingtracker lookup proxy on :${port} (provider: ${process.env.PROVIDER || 'stub'})`));
}
