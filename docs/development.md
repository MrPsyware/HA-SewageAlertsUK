# How Sewage Alerts UK works

## From a location to a watch

The config flow offers an upstream watch, a coastal watch and a single-outfall search. Location-based setup checks every supported company's feed, lets the user review the matches, and saves the selected sites in the config entry. A failed company lookup prevents confirmation of a partial selection. A watch needs 1–100 matches. The user can adjust the range and try again. [Location flow](../custom_components/sewage_alerts_uk/location_flow.py)

**River watches** start with OS Open Rivers sections near the chosen point. The integration projects coordinates into local metres, snaps the point onto the selected section and follows connected links backwards using their node IDs and explicit flow direction. It includes tributaries and connected lake links, clips the first section at the selected point, and measures distance along the polylines. Tidal rivers, canals and links with unknown flow are excluded. [River tracing](../custom_components/sewage_alerts_uk/river.py)

Each outfall is matched to the nearest mapped link within 100 m. The search includes neighbouring and downstream links. If the two closest links differ in snap distance by less than 10 m, the match is ambiguous and is omitted. An outfall is kept only if its position lies within the traced upstream range. Generalised geometry, missing streams and imprecise site coordinates can leave genuine upstream outfalls out of the selection.

**Coastal watches** use straight-line distance from the chosen location. Discovery requests an enclosing box from the water-company layers, then checks each site's great-circle distance against the radius. Receiving-water names are kept for display. The selection can include inland outfalls and does not account for tides or plume direction.

**Single-outfall entries**, including those created with v0.1, store a company and site ID. Site IDs are stable within a provider. The ArcGIS object ID is unsuitable as a persistent identifier. [Feed client](../custom_components/sewage_alerts_uk/api.py)

## Polling and entity states

Each watch polls every 15 minutes, batching its selected site IDs by company and following ArcGIS pagination where needed. Polling uses the saved selection. Geocoding and river tracing run only during setup. Recorder can keep observed state changes according to the user's settings. There is no historical backfill, and brief events can fall between polls.

The feed client normalises field casing and decodes ArcGIS timestamps as UTC milliseconds. Provider status codes are `1` (discharging), `0` (inactive) and `-1` (offline). Other values are unknown. Some providers update `LastUpdated` only on a state change, so its age alone cannot establish that a report is stale. [Discharge data and parsing](../custom_components/sewage_alerts_uk/api.py)

| Watch entity | Value |
| --- | --- |
| Upstream discharging / Coastal discharging | On if any selected site reports a discharge. Off requires an inactive report from every site. Otherwise unknown. |
| Upstream status | `discharging`, `no_reported_discharges` or `unknown`. |
| Reported active outfalls | Count of known active sites. This is a lower bound when reports are missing. |
| Outfalls with unknown status | Count of missing, offline or unrecognised reports, including failed company requests. |
| Latest discharge / Latest discharge duration | Start and duration of the most recently started reported event. Active durations tick every minute. |
| Possible contamination | On during a reported discharge or a known post-discharge window. Incomplete reports can leave it unknown. |
| Estimated contamination until / remaining | Latest reported end plus the configured window, and seconds remaining. An active discharge or incomplete report leaves the end unknown. |

A failed single-outfall request makes that entry's entities unavailable. For grouped watches a provider failure marks its affected sites unknown. Watch attributes list failed companies and include per-site status, company, watercourse, distance and discharge timing. The latest end timestamp may belong to an earlier event while a new discharge is active. [Watch aggregation](../custom_components/sewage_alerts_uk/watch.py)

The precautionary window is configurable from 24 to 168 hours. The four-day default draws on Thames Water's guidance. Overflow reports contain no measurements of bacteria, discharge volume or dilution. [Thames Water storm discharge guidance](https://www.thameswater.co.uk/about-us/performance/river-health/frequently-asked-questions/information-about-storm-discharge)

## Data sources and attribution

- The nine water-company layers are published via Stream's National Storm Overflow Hub. Preserve company attribution and check each layer's terms when redistributing data. [Provider endpoints](../custom_components/sewage_alerts_uk/providers.json) · [National Storm Overflow Hub](https://www.arcgis.com/apps/mapviewer/index.html?webmap=d0d61f9f88a34ef5adb83dbff938c537)
- River geometry comes from an ArcGIS-hosted copy of OS Open Rivers. Contains OS data © Crown copyright and database right 2026 under the Open Government Licence v3.0. [OS Open Rivers](https://www.ordnancesurvey.co.uk/products/os-open-rivers) · [Hosted layer](https://services.arcgis.com/qHLhLQrcvEnxjtPr/arcgis/rest/services/OS_OpenRivers/FeatureServer/0) · [Licence](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
- Postcodes.io resolves UK postcodes and searches OS Open Names for towns and villages. [Postcodes.io data licences](https://postcodes.io/docs/licences/)
- SewageMap inspired the project. This integration queries public sources independently. [SewageMap](https://www.sewagemap.co.uk/) · [Source acknowledgements](https://github.com/AlexLipp/sewage-map) · [Artwork provenance](../assets/README.md)

## Working on the integration

The offline suite uses Home Assistant classes and recorded responses from the nine company feeds. Tests cover flow direction, tributaries, bends, ambiguous matches, setup, partial failures and aggregate states. The opt-in smoke test follows a public Shrewsbury location through upstream discovery. [Local test commands](../CONTRIBUTING.md#local-checks) · [Marketplace submission](marketplace.md)
