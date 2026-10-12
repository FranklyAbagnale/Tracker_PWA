/** Picks the provider adapter named by env.PROVIDER (default "stub"). */

import * as stub from './stub.js';
import * as mock from './mock.js';

// Register real adapters here, e.g.  import * as acme from './acme.js';  and add  acme  below.
const PROVIDERS = { stub, mock };

export function getProvider(name) {
  return PROVIDERS[String(name || 'stub').toLowerCase()] || null;
}
