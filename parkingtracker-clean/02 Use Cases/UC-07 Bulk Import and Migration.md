---
tags: [usecase]
id: UC-07
actor: Data owner
priority: M
status: implemented
---
            
# UC-07 — Bulk Import and Migration

## Goal
Move an existing XML database into the per-record JSON structure.

## Main flow
1. Owner runs:
   python scripts/migrate_xml_to_json.py --in import/export.xml --media-root import
   (writes into data/, photos/ and reports/ of the repository; see
   07 Operations/Runbook - XML Import.md)
2. Script parses the XML with xml.etree.ElementTree.
3. For each vehicle node, script maps fields to the JSON schema.
4. Script writes one file per plate into data/plates/.
5. Script reports collisions (two XML nodes mapping to the same normalised
   plate) and merges them, preferring the later updated.
6. Script runs build_index.py to regenerate data/index.json.
7. Owner reviews git status, spot-checks a sample, then commits.

## Alternate flows

A1 Photo references. Photo paths pointing at remote URLs are downloaded into
photos/ and rewritten to repository-relative paths, unless --keep-remote.

A2 Encoding issues. Non-UTF-8 XML. Script attempts latin-1 fallback and
warns.

A3 Duplicate plates. Merged record written to reports/merges.csv for review.

## Acceptance criteria
- [ ] Every XML vehicle maps to exactly one JSON file or a documented merge.
- [ ] No field silently dropped; unmapped fields go to a reports/ file.
- [ ] Migrated records validate against the schema.
- [ ] The app reads the migrated data with no code changes.
