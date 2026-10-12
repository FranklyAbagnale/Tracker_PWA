export const appState = {
  currentVehicle: null,
  editingSightingId: null,    // sighting being edited on the edit screen
  currentView: 'home-screen',
  localUserLocation: null,
  returnTo: 'vehicle-form',   // where photo capture hands back to
  draft: {},                  // form values preserved across the photo screen
  blobUrls: [],               // object URLs to revoke on navigation
  lookups: {}                 // plate key -> proxy answer, so a plate is looked up once per session
};
