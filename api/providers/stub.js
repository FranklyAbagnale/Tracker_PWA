/**
 * Placeholder provider. Ships as the default so the app and proxy can be deployed before a provider is chosen:
 * every lookup answers "not configured" and the app simply hides the feature's results.
 *
 * To connect a real provider, copy this file (for example to providers/acme.js), implement lookup(),
 * and register it in providers/index.js. Contract:
 *
 *   lookup({ state, plate, env }) -> { year, make, model } | null
 *
 *   - state: two-letter code, already validated against ALLOWED_STATES (California only by default)
 *   - plate: upper-case letters and digits, 1-10 characters
 *   - env:   the proxy's environment; read the API key from env.PROVIDER_KEY (a secret, never in the repo)
 *   - return null when the provider has no match
 *   - throw ProviderError (errors.js) on provider failures
 *   - return ONLY year, make and model. Anything else the provider sends (VIN, owner, address) is
 *     dropped by the handler's sanitiser, and adapters should not pass it along either.
 */

import { NotConfiguredError } from '../errors.js';

export async function lookup() {
  throw new NotConfiguredError();
}
