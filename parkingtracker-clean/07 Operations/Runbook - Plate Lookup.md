---
tags: [runbook, operations]
---

# Runbook — Plate Lookup

Year, make and model for a California plate, through a small proxy that holds the provider's API key.
Design and limits: `04 Decisions/ADR-010 Plate Lookup via Proxy.md`.

The feature is **off** until `LOOKUP_URL` is set in `web/js/config.js`. With it off nothing in the app changes.

## Manual lookup (no proxy, no key)
When a plate search finds nothing, a button per site in `PLATE_SITES` (`web/js/config.js`) appears under "Create new vehicle": FaxVIN, Carfax, EpicVIN, FindByPlate. Each copies the plate and opens the site in a new tab. FindByPlate is opened at its report page for the state and plate; the others open their plate-lookup page and you paste the plate.

Sites marked `tracked: true` (FaxVIN, Carfax) get a Verified / Not found / Wrong choice on the vehicle forms, saved as `siteChecks` with the date. The Year field appears only once a tracked site is Verified, and a year cannot be saved without one (an unchanged saved year stays valid). Make and model are typed as usual. None of this is the verified `plateLookup` from the proxy.

To try another site, add a line to `PLATE_SITES`; set `tracked: true` to give it a status choice.

## 1. Choose a provider
Candidates found when this was written (check current terms and prices yourself):

| Provider | Returns | Notes |
|---|---|---|
| VehicleDatabases | VIN, make, model, year | California confirmed; states it returns no owner data; free test credits |
| CarAPI | year, make, model, trim, VIN, engine | "50 US states"; pay per lookup |
| CarsXE | VIN, make, model, trim, engine | California not stated on its page |

Before using any of them, read their terms on **storing results and on permissible use**. The app saves year,
make and model into a public repository (no VIN, no owner), so confirm that is allowed or make the repo private.

## 2. Write the adapter
Copy `api/providers/stub.js` to `api/providers/<name>.js`, implement `lookup({ state, plate, env })`, return
`{ year, make, model }` (or `null` for no match), and register it in `api/providers/index.js`. Read the key from
`env.PROVIDER_KEY`. Use `api/providers/mock.js` to see the expected shape. Run `npm test` (the handler tests use the mock).

## 3a. Deploy as a Cloudflare Worker
```bash
cd api
npx wrangler login
npx wrangler secret put PROVIDER_KEY        # paste the provider's key; it is never in the repo
# edit wrangler.toml: PROVIDER = "<name>", ALLOWED_ORIGIN = "https://<your-pages-origin>", DAILY_LIMIT
npx wrangler deploy
```
It prints the Worker URL (`https://parkingtracker-lookup.<account>.workers.dev`).

## 3b. Or run it on an internal host
```bash
PROVIDER=<name> PROVIDER_KEY=... ALLOWED_ORIGIN=https://<your-pages-origin> DAILY_LIMIT=200 PORT=8787 node api/serve-node.mjs
```
Testers' phones must reach it over **HTTPS** (VPN, tunnel or reverse proxy). Browsers block plain-http calls from the app.

## 4. Turn it on in the app
In `web/js/config.js` set `LOOKUP_URL` to the proxy URL, then add the same origin to `connect-src` in
`web/index.html` (for example `connect-src 'self' https://api.github.com https://parkingtracker-lookup.<account>.workers.dev`).
`npm test` fails if the URL's origin is missing from `connect-src`. Push; Pages redeploys.

## What the app does with it
- **Search for a California plate that is not listed**: looks it up and offers the make and model on "Create new vehicle".
- **New-vehicle form**: typing a California plate checks whether it is on file; if not, looks it up and fills blank make and model.
- **Open a vehicle whose make or model is unknown** (for example XML imports): looks up its California plate and fills the blanks.
- **Open a vehicle with known details**: no automatic lookup; "Check against registration data" does it on request.
- **Saving**: the vehicle gets `plateLookup` only when make and model both match the answer. A difference is shown and nothing is stored.

## Cost and abuse controls
- The proxy only answers callers whose GitHub token can write to the repository.
- Answers are cached (found 30 days, not found 1 day) and the app asks once per plate per session.
- `DAILY_LIMIT` caps provider calls per UTC day per instance (a Worker may run several instances, so treat it as approximate).
- Lookups cover only the states in `ALLOWED_STATES` (default `CA`).

## Turn it off
Set `LOOKUP_URL = ''` and push. Stored `plateLookup` fields stay on the records; they are harmless.
