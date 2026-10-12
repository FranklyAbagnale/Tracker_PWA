---
tags: [testing, phone, sample-data]
---

# Phone Test with Sample Data

A scripted pass on a real iPhone (Safari) and a real Android phone (Chrome),
using the deterministic sample set from `scripts/generate_sample_data.py`.
Expected results below are asserted by `tests/e2e_sample_data.py` in desktop
Chromium; the phone run adds what a desktop cannot: real camera, real GPS, real
touch, iOS quirks.

## 1. Get the data and app live

1. Apply the patches and push to `main` (the sample data is its own commit, so
   you can leave it out and generate locally instead).
2. **Settings -> Pages -> Source: GitHub Actions**; wait for `pages.yml`.
3. Make a fine-grained token: this repo only, **Contents: Read and write**.
4. Open `https://<owner>.github.io/ParkingTracker/` on the phone, paste the token.
   iOS: Share -> Add to Home Screen.

**Testing somewhere other than Pasadena?** Regenerate around where you will
stand, then push:

```bash
python3 scripts/generate_sample_data.py --center <lat>,<lng>
```

Regenerating replaces the old sample set (it never accumulates). Timestamps are
relative to "now", so regenerate if the data is more than ~2 days old; a phone
that already cached the index needs **Refresh index** on the Local page.

## 2. The sample set

18 fake vehicles, plates `TST*` / `DLRTST1`, each photo watermarked
"SAMPLE DATA". Distances are from the centre point.

| Vehicle | Plate | Flag | Last seen | Distance | Why it exists |
|---|---|---|---|---|---|
| Red Honda Civic | TST1001 | confirmed | 2 h | 120 m | recent hot, 2 sightings, photos |
| Silver Honda Accord | TST8001 + DLRTST1 (dealer) | suspected | 6 h | 350 m | multi-plate |
| White Ford F-150 | TST1002 | suspected | 20 h | 400 m | recent hot |
| Tan Toyota Tacoma | TST9001 | suspected | 8 h | 450 m | **moved**: older sighting 2.2 km away |
| Black Tesla Model 3 | TST1003 | suspected | 40 h | 850 m | recent hot, near the edge |
| Silver Toyota Camry | TST2001 | confirmed | 4 d | 300 m | older hot |
| Blue Subaru Outback | TST2002 | suspected | 10 d | 700 m | older hot |
| Green Jeep Wrangler | TST3001 | unknown | 1 d | 200 m | unknown tier |
| Teal Hyundai Elantra `<i>GT</i>` | TST9002 | unknown | 12 h | 280 m | HTML in name + notes |
| Brown Ford Transit | none | unknown | 5 h | 300 m | photo-first, no plate |
| Grey Nissan Pathfinder | TST3002 | unknown | 6 d | 500 m | unknown tier |
| Yellow Mini Cooper | TST4001 | cleared | 3 d | 150 m | cleared |
| White Chevrolet Express | TST4002 | cleared | 30 d | 600 m | cleared, **older than 14 d but still shown** |
| Black Dodge Charger | TST4101 | pigs | 2 d | 250 m | pigs, mixed in with cleared by distance |
| White Chevrolet Tahoe | TST4102 | pigs | 25 d | 900 m | pigs, **older than 14 d but still shown** |
| Orange Dodge Challenger | TST5001 | confirmed | 20 d | 250 m | **hidden** (confirmed and older than 14 d) |
| Purple Kia Soul | TST6001 | confirmed | 3 h | 2.5 km | **outside** the 1 km radius |
| Black BMW 3 Series | TST7001 | suspected | 1 h | none | **no location**: plate search only |

## 3. Read-only checks

### Home screen
- [ ] Top third: state and plate entry with a Search button. Enter also searches; no separate page
- [ ] Middle third: large **Take photo** button. It opens the phone's own camera app; after the shot the
      vehicle form opens with the photo attached and any plate already typed
- [ ] Bottom third: the **Nearby** list appears by itself once location is allowed, same order as below,
      with circles: red confirmed, orange suspected, green cleared, blue pigs, yellow unknown
- [ ] Walk or drive about 50 m (or change the simulated location): the list re-sorts without a button press
- [ ] A partial plate (e.g. `TST`) lists matches in the bottom third; **Clear** returns to Nearby
- [ ] Menu: **Add vehicle (no photo)**, **Tutorial**, **Glossary**, **Sync now**, **Log out**. There is no classic-home switch and no Nearby (manual location); use **Local** on the home screen for a manual location
- [ ] Back arrow (left of the pin): not shown on first open; open Plate search, tap the logo, then the arrow returns to the search; after going back it is hidden again
- [ ] **Tutorial** and **Glossary** each open in a new tab with a link back to the app; the glossary filter narrows the list

### Local (from the centre point)
Use **Enter coordinates** with the centre for exact distances. GPS drifts by
10-30 m, so near-ties (Elantra 280 m vs Transit 300 m) may swap when using GPS.

- [ ] **Use my location** prompts for permission; allow it
- [ ] **10** cards at first, then a **View 5 more** button; after tapping it, **15** cards in this order
  (flag first, nearest first within a flag):
  1. Red Honda Civic  2. Silver Toyota Camry  (confirmed)
  3. Silver Honda Accord  4. White Ford F-150  5. Tan Toyota Tacoma
  6. Blue Subaru Outback  7. Black Tesla Model 3  (suspected)
  8. Yellow Mini Cooper  9. Black Dodge Charger  10. White Chevrolet Express
  11. White Chevrolet Tahoe  (cleared and pigs, mixed by distance)
  12. Green Jeep Wrangler  13. Teal Hyundai Elantra  14. Brown Ford Transit
  15. Grey Nissan Pathfinder  (unknown, always last)
- [ ] Card edge colours: red = confirmed, amber = suspected, grey = unknown, green = cleared, blue = pigs
- [ ] Not listed: Orange Dodge Challenger, Purple Kia Soul, Black BMW 3 Series
- [ ] Search from 2.5 km north of the centre: Purple Kia Soul appears
- [ ] **Refresh index** shows "Index refreshed just now"
- [ ] Deny location permission: you get a message and can still type coordinates

### Plate
- [ ] `tst-1001` (any case, hyphen) opens Red Honda Civic with 2 sightings, newest first, and 2 photos
- [ ] `DLRTST1` opens the Silver Honda Accord (second plate on the same vehicle)
- [ ] `TST7001` opens the BMW and its history says "no location"
- [ ] `TST1O01` (letter O): "No vehicle found", suggests Red Honda Civic; tap it
- [ ] `ZZZ9999`: not found, offers **Create new vehicle with this plate**
- [ ] `TST9002`: the name shows literally as `Elantra <i>GT</i>` (no italics) and the note shows `<script>alert(1)</script>` as text, with no popup

## 4. Write checks (these create real records)

Records you create here are normal records (not tagged as sample data). Start
the notes with `TEST` so you can find and delete them.

- [ ] **Photo**: camera opens on the back camera; **Capture**, **Accept**, **Capture**, **Accept**; two thumbnails; remove one with the red x; **Done**
- [ ] Form keeps what you typed after **Add photos** and back
- [ ] **Vehicle**: save with a new plate `TST0001`, location ticked; the home screen says saved, then "All synced"
- [ ] Open the new vehicle from Local: photo is the right way round (plate text not reversed) and the sighting has a location
- [ ] **Plate** `TST1001` -> change flag to cleared, add a note, save; it moves to the cleared group in Local
- [ ] Add plate `TST0002` to an existing vehicle; then try adding `TST1001` to a different vehicle and confirm it is refused
- [ ] **Offline**: airplane mode, save a vehicle; home shows "Waiting to upload: 1 pending"; turn airplane mode off; it uploads by itself
- [ ] Two phones (or phone + desktop): edit the same vehicle at once; both sightings survive
- [ ] Add to Home Screen, launch from the icon: opens full-screen, works with the network off after one online load

## 5. Cleanup, then real data

```bash
python3 scripts/generate_sample_data.py --clean   # removes only records tagged sample-data
git rm data/vehicles/<your TEST records>.json data/plates/TST000*.json photos/<their photos>
git commit -am "Remove sample and test data" && git push
```

`--clean` removes the sample vehicles, their plates and photos, and rebuilds
`data/index.json`. Anything created in the app is left alone, which is why the
write checks use a `TEST` prefix.

## Related
- Manual Test Checklist
- Known Failure Modes
- Deployment Guide
