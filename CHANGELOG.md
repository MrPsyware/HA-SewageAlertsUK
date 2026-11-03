# Changelog

## 0.5.1 — 2026-11-03

- Replace location-specific dashboard and test examples with generic placeholders.

## 0.5.0 — 2026-11-03

- Add a map marker for every monitored outfall.
- Expose outfall status, discharge timing and contamination-window attributes
  through Home Assistant's native geolocation source.
- Add a native Map card and details-card example to the README.

## 0.4.0 — 2026-11-03

- Add a configurable precautionary contamination window to river and coastal watches.
- Add `Possible contamination`, `Estimated contamination until`, and
  `Estimated contamination remaining` entities.
- Default the window to 96 hours, with a 24–168 hour setup range.
- Keep the estimate explicitly separate from measured water quality.

## 0.3.0 — 2026-10-04

- Add coastal-area watches alongside river/upstream watches.
- Choose a coastal radius around a postcode, town, home location or coordinate.
- Group nearby coastal outfalls into one automation-friendly watch device.
- Preserve receiving-water names, coordinates and distances for each coastal outfall.
- Document the coastal limitations: radius matching does not model tides, currents,
  plume direction or bathing-water quality.

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
