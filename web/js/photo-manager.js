/**
 * photo-manager.js
 * Camera access, capture, compression, and the in-memory photo collection.
 * Photos live in memory until a vehicle record is saved.
 */

import { PHOTO_MAX_BYTES, PHOTO_MAX_EDGE, MAX_PHOTOS_PER_SIGHTING } from './config.js';

const state = {
  stream: null,
  pending: null,   // captured but not yet accepted
  selected: []     // accepted data URLs
};

// ---------- camera ----------

export async function initializeCamera(videoElement) {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
    audio: false
  });
  state.stream = stream;
  videoElement.srcObject = stream;
  await videoElement.play();
  return stream;
}

export function stopCamera() {
  if (state.stream) {
    state.stream.getTracks().forEach((track) => track.stop());
    state.stream = null;
  }
}

// ---------- compression ----------

function dataUrlBytes(dataUrl) {
  return Math.floor((dataUrl.length - dataUrl.indexOf(',') - 1) * 0.75);
}

/** Scale to PHOTO_MAX_EDGE and lower JPEG quality (then size) until under PHOTO_MAX_BYTES. */
function compressToJpeg(source, width, height) {
  let scale = Math.min(1, PHOTO_MAX_EDGE / Math.max(width, height));
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  let dataUrl = '';

  for (let pass = 0; pass < 4; pass++) {
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
    for (const quality of [0.85, 0.75, 0.65, 0.55]) {
      dataUrl = canvas.toDataURL('image/jpeg', quality);
      if (dataUrlBytes(dataUrl) <= PHOTO_MAX_BYTES) return dataUrl;
    }
    scale *= 0.8;
  }
  return dataUrl;
}

/** Capture the current video frame (not mirrored, so plate text reads correctly). */
export function captureFrame(videoElement) {
  const width = videoElement.videoWidth;
  const height = videoElement.videoHeight;
  if (!width || !height) throw new Error('Camera is not ready yet');
  const dataUrl = compressToJpeg(videoElement, width, height);
  state.pending = dataUrl;
  return dataUrl;
}

/** Use a file from the camera app or photo library (honours EXIF rotation). */
export async function captureFromFile(file) {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  try {
    const dataUrl = compressToJpeg(bitmap, bitmap.width, bitmap.height);
    state.pending = dataUrl;
    return dataUrl;
  } finally {
    bitmap.close();
  }
}

// ---------- collection ----------

export function getPendingCapture() { return state.pending; }
export function discardPendingCapture() { state.pending = null; }

/** Move the pending capture into the collection. Returns false if full or nothing pending. */
export function acceptPendingCapture() {
  if (!state.pending || state.selected.length >= MAX_PHOTOS_PER_SIGHTING) return false;
  state.selected.push(state.pending);
  state.pending = null;
  return true;
}

export function removeCapturedPhoto(index) { state.selected.splice(index, 1); }
export function getCapturedPhotos() { return state.selected; }

export function clearCapturedPhotos() {
  state.selected = [];
  state.pending = null;
}
