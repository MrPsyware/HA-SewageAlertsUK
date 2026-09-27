# Sewage Alerts UK

![Sewage Alerts UK — Know what’s flowing upstream.](https://raw.githubusercontent.com/MrPsyware/HA-SewageAlertsUK/main/assets/banner.png)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/MrPsyware/HA-SewageAlertsUK)
[![Validate](https://github.com/MrPsyware/HA-SewageAlertsUK/actions/workflows/validate.yml/badge.svg)](https://github.com/MrPsyware/HA-SewageAlertsUK/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/MrPsyware/HA-SewageAlertsUK)](https://github.com/MrPsyware/HA-SewageAlertsUK/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-teal.svg)](LICENSE)

A Home Assistant custom integration that monitors reported sewage discharges
**upstream of a chosen point on your local river**. No account or API key is
required. Current discharge feeds cover nine English water companies.

## Install through HACS

Requires **Home Assistant 2026.9.4 or later** and a working HACS installation.

[![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MrPsyware&repository=HA-SewageAlertsUK&category=integration)

Or add it manually:

1. Open **HACS → ⋮ → Custom repositories**.
2. Enter `https://github.com/MrPsyware/HA-SewageAlertsUK` and select **Integration**.
3. Find **Sewage Alerts UK**, download the latest release, then restart Home Assistant.
4. Follow the configuration steps below.

This is a **custom repository**, not yet part of the HACS default catalogue.
HACS handles updates from this repository's GitHub releases. Icons are bundled
with the integration for Home Assistant; the HACS catalogue may show a generic
icon depending on the HACS version.

## Manual installation

1. Download the source ZIP from the [latest release](https://github.com/MrPsyware/HA-SewageAlertsUK/releases/latest).
2. Copy `custom_components/sewage_alerts_uk` from the extracted archive to
   `/config/custom_components/sewage_alerts_uk` on Home Assistant.
3. Restart Home Assistant.

## Configure

[![Add the integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=sewage_alerts_uk)

1. Open **Settings → Devices & services → Add integration → Sewage Alerts UK**.
2. Use your **Home Assistant home location**, enter a **postcode**, search for a
   **town/village**, or enter **latitude and longitude**. Coordinates are prefilled
   from your HA home location and can be adjusted.
3. Confirm the location result for a postcode/town search.
4. Choose a nearby **river section**. The nearest supported section is the default;
   its coordinates and distance from your location are shown. If needed, use
   coordinates for the particular stretch of river you care about.
5. Set the **upstream distance**, from 1 to 25 km (default 10 km). This measures
   distance along the river, including connected tributaries, not a circular radius.
6. Review the matched upstream outfalls and confirm.

The integration searches across all supported companies; you do not need to know
which company operates an outfall. A failed company lookup blocks initial
confirmation rather than silently creating an incomplete selection.

The selected outfalls are saved when the watch is created. To change its location,
range, or discover newly added outfalls, remove the watch and create it again.
Existing individual-outfall entries from v0.1 continue to work. The setup menu
retains **Choose an individual outfall (advanced)** for manual monitoring.

Tested with Home Assistant Core 2026.9.4. This is an early release; review the
matched outfalls and the coverage limitations below before using automations.

## Entities and automations

Each upstream watch creates one device with:

| Entity | Meaning |
| --- | --- |
| Upstream discharging | `on` if any selected outfall reports a discharge; `off` only when all selected outfalls have usable reports saying they are not discharging; otherwise `unknown` |
| Upstream status | `discharging`, `no_reported_discharges`, or `unknown` |
| Reported active outfalls | Count of selected outfalls with usable reports of active discharge; a lower bound when data is missing |
| Outfalls with unknown status | Count with stale, offline, missing or unavailable reports |

Attributes include the monitored outfalls, company, receiving watercourse,
upstream distance, current status, and any companies whose requests failed.
Individual company failures do not hide a known discharge from another company.

Example: replace the entity ID below with your watch's binary sensor. This alerts
when an `on` state is newly observed, including after a monitoring outage.

```yaml
alias: Upstream sewage discharge alert
triggers:
  - trigger: state
    entity_id: binary_sensor.river_severn_upstream_upstream_discharging
    to: "on"
actions:
  - action: persistent_notification.create
    data:
      title: Upstream sewage discharge reported
      message: >-
        {{ trigger.to_state.name }} is reporting an upstream discharge.
        Check the watch's outfall statuses for details.
mode: single
```

You can also select the entity in Home Assistant's automation editor. Use the
unknown-status count for a separate monitoring-problem alert.

Manual outfall entries retain five entities: Discharging, Status, Latest discharge
start, Latest discharge end, and Source last updated. The latest end timestamp
may belong to a previous discharge while a new one is active.

## How upstream selection works

The integration queries an ArcGIS-hosted copy of **OS Open Rivers**, snaps your
chosen location onto the selected river section, and walks the river links
backwards using their start/end nodes and explicit flow direction. It includes
connected tributaries and river links through lakes, and clips the selection at
the chosen point and upstream distance. Tidal links, canals and links without a
supported flow direction are not traced.

Outfalls are matched to their nearest mapped river link within 100 metres. This
search considers all nearby links, not only the upstream links, so downstream
outfalls and neighbouring rivers are not incorrectly pulled into the upstream
selection. Matches with another river link within 10 metres of the best match's
snap distance are excluded as ambiguous, including some confluence locations.
Distances are approximate, using a local metre projection and river polylines.

**This is a mapped estimate, not exhaustive upstream coverage.** The open river
network is generalised: small streams, culverts, unmapped connections and distant
outfall coordinates can be missed. Ambiguous matches are intentionally omitted.
Review the selected outfalls; zero matches does not imply zero discharge. The
setup will not create a watch with zero matched outfalls.

Reports describe storm-overflow activity, not sewage concentration, pollutant
travel time or measured river water quality. `off` means no selected monitor is
currently reporting a discharge, not that a river is clean. This does not
reproduce SewageMap's downstream-impact model.

## Updates and missing data

The selected outfalls are polled every 15 minutes, with one query per company.
Requests have timeouts and handle ArcGIS pagination. Monitoring does not repeat
location lookups or river-network downloads.

An offline monitor, unknown status, missing update time, missing outfall or failed
company request is treated as unknown by the upstream watch. Reports older than
24 hours are conservatively marked stale on the next poll. This is an integration
policy, not a provider guarantee: some companies may update individual records
only when something changes. Source data can also be delayed.

A failed request for a manual single-outfall entry makes its entities unavailable.
Home Assistant records observed changes according to Recorder settings; there is
no historical backfill, and brief events between polls can be missed.

## Coverage, data and privacy

Supported discharge feeds: Anglian Water, Northumbrian Water, Severn Trent Water,
South West Water, Southern Water, Thames Water, United Utilities, Wessex Water and
Yorkshire Water. Welsh, Scottish and Northern Irish providers are not included.
Cross-border upstream catchments may therefore have incomplete discharge coverage.

- Overflow data: individual companies through Stream's
  [National Storm Overflow Hub](https://www.arcgis.com/apps/mapviewer/index.html?webmap=d0d61f9f88a34ef5adb83dbff938c537).
  Public layer URLs are recorded in `providers.json`. Retain company attribution
  when sharing their data and consult each layer's licensing terms.
- River mapping: [OS Open Rivers](https://www.ordnancesurvey.co.uk/products/os-open-rivers),
  queried via [this ArcGIS layer](https://services.arcgis.com/qHLhLQrcvEnxjtPr/arcgis/rest/services/OS_OpenRivers/FeatureServer/0).
  Contains OS data © Crown copyright and database right 2026, under the
  [Open Government Licence](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
  The hosted service is an external dependency and may change or become unavailable.
- Postcodes and towns: [Postcodes.io](https://postcodes.io/), using its postcode
  lookup and OS Open Names place search. See its [data licences](https://postcodes.io/docs/licences/).

Postcode/town searches are sent to Postcodes.io only during setup. Location
coordinates are sent to the river and company mapping services for spatial
queries. The saved watch stores the selected river point and outfalls, not the
original postcode or town query. Direct coordinates skip geocoding.

Inspired by [SewageMap](https://www.sewagemap.co.uk/) and its
[documented data sources](https://github.com/AlexLipp/sewage-map). This project is
independent of SewageMap and does not copy its code or use private endpoints.

## Development

```sh
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Tests cover graph direction, tributaries, same-link downstream exclusion, distance
along bends, cycles, ambiguous snapping, geocoding, setup flows, source failures,
and conservative aggregate states. They use real Home Assistant classes and
recorded public overflow samples retrieved on 27 September 2026.

Optional public-service smoke test (uses Shrewsbury, not your home location):

```sh
.venv/bin/python -m pytest tests/test_live.py --run-live -qs
```

## Support and licence

Report problems through [GitHub issues](https://github.com/MrPsyware/HA-SewageAlertsUK/issues).
See [release notes](CHANGELOG.md), [contribution guidance](CONTRIBUTING.md),
and [artwork and generation prompts](assets/README.md).
Original code is MIT licensed; external datasets retain their own licences (see [NOTICE](NOTICE)).
