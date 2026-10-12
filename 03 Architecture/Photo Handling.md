---
tags: [architecture, photos]
---

# Photo Handling

## Capture

~~~html
<input type="file" accept="image/*" capture="environment">
~~~

capture="environment" opens the rear camera directly on both platforms.
Omitting it lets the user choose camera or gallery. Support both.

## Downscale before upload
Phone cameras produce 3-12 MB images. Downscale client-side:

~~~js
async function downscale(file, maxEdge = 1600, quality = 0.8) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
  const w = Math.round(bitmap.width * scale);
  const h = Math.round(bitmap.height * scale);
  const canvas = new OffscreenCanvas(w, h);
  canvas.getContext('2d').drawImage(bitmap, 0, 0, w, h);
  return canvas.convertToBlob({ type: 'image/jpeg', quality });
}
~~~

Target: <= 1600 px on the long edge, <= 500 KB.

## Storage
Photos live as real files in photos/, referenced by relative path. Not
base64 in the JSON. Path convention: photos/<PLATE>.jpg.

## Upload
Photos uploaded via the same PUT /contents/ call as records, base64-encoded.
Upload the photo first, then the record that references it.

## Size budget

| Records | Photo size | Repo size | Verdict |
|---|---|---|---|
| 1,000 | 200 KB | ~200 MB | Fine |
| 5,000 | 200 KB | ~1 GB | Getting heavy |
| 10,000+ | 200 KB | 2 GB+ | Move to object storage |
