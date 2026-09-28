# Changelog

## 0.2.1 — 2026-09-28

- Treat provider `Status` as the current state even when event-driven
  `LastUpdated` timestamps are old.
- Add latest discharge and discharge duration sensors for individual outfalls
  and upstream watches.
- Active discharge durations update every minute without extra provider API calls.
- Include per-outfall latest discharge and duration attributes on upstream watches.

## 0.2.0 — 2026-09-28

First public release, installable as a HACS custom repository.

- Set up monitoring from a home location, postcode, town, or coordinates.
- Select a river section and trace 1–25 km upstream, including tributaries.
- Combine discharge reports into automation-friendly upstream entities.
- Distinguish inactive outfalls from missing, offline and stale reports.
- Support nine English water-company feeds and manual outfall monitoring.
- Include local Home Assistant brand icons and project banner artwork.
- Add HACS metadata, installation links, tests and validation workflows.

Known limits: generalised river mapping and incomplete provider coverage can
omit discharges. Outfall matching is a mapped estimate, not a water-quality
measurement. See the README for details.
