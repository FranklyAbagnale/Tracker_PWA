---
tags: [architecture, geo]
---

# Geolocation and Proximity

## Getting the position

~~~js
navigator.geolocation.getCurrentPosition(onSuccess, onError, {
  enableHighAccuracy: true,
  timeout: 10000,
  maximumAge: 0
});
~~~

Hard requirement: HTTPS. GitHub Pages satisfies this automatically.
Consent is mandatory. Treat denial as a normal path, not an error.

## Accuracy in practice

| Condition | Typical accuracy |
|---|---|
| Clear sky, GPS lock | 5-20 m |
| Urban canyon | 20-100 m |
| Indoors, WiFi-assisted | 30-150 m |
| Indoors, cell only | 500 m+ |

Because accuracy can be worse than your search radius, always compare
accuracy to radius. If accuracy > radius, say so in the UI.

## Distance calculation

~~~js
function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = d => d * Math.PI / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat/2)**2 +
            Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
            Math.sin(dLon/2)**2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
~~~

## Making it fast
Two-stage filter:
1. Bounding box — cheap comparison on lat/lng using a degree delta.
2. Haversine — exact distance on the survivors, then sort.

## Storing location
- Store raw lat/lng plus accuracy.
- Never store a single "40.7,-74.0" string.
- Consider rounding to 5 decimal places (~1 m).
