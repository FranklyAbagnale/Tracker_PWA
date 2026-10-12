/** Cloudflare Worker entry. Deploy with `npx wrangler deploy` from this folder (see wrangler.toml). */

import { handleLookup } from './lookup.js';

export default {
  fetch: (request, env) => handleLookup(request, env)
};
