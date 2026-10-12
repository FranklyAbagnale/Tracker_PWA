# photos/ — sighting photos

One JPEG per photo, named by the app (`VEH_<key>_<time>_<n>.jpg`), referenced from the `photos` list of a sighting in `../data/vehicles/`. Photos are separate files, never embedded in JSON (`04 Decisions/ADR-008 Photos as Files not Base64.md`).

- The folder is empty until the app saves photos or a legacy-media import is run (`../tools/README-xml-converter.md`; the CSV converter never imports photos).
- The app scales photos to 1600 px on the long edge and under 500 KB before upload.
- `npm run validate` warns about a sighting that references a missing photo.
- `.gitkeep` only keeps the empty folder in Git.
- Photos grow the repository quickly. If this becomes a problem, the plan is a separate photo repository (see `08 Roadmap/`).
