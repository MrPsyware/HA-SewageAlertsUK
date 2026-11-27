# Alerts and dashboards

## Discharge notification

Replace the entity ID below with your watch's binary sensor. This alerts
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

## Map and outfall details

A marker changes source when its outfall starts or stops reporting a discharge. Include both sources to show every monitored outfall. These sources include outfalls from all your watches.

```yaml
type: map
title: Nearby sewage outfalls
geo_location_sources:
  - sewage_alerts_uk
  - sewage_alerts_uk_active
auto_fit: true
hours_to_show: 0
```

To show only outfalls currently reporting a discharge, use the active source:

```yaml
type: map
title: Active sewage discharges
geo_location_sources:
  - sewage_alerts_uk_active
auto_fit: true
hours_to_show: 0
```

Each marker includes the site ID, company, receiving watercourse, current status,
last discharge start, event duration, and estimated contamination window. A details
card can sit beside the map (replace the entity IDs with your watch):

```yaml
type: entities
title: River Example sewage watch
show_header_toggle: false
entities:
  - binary_sensor.example_river_upstream_discharging
  - binary_sensor.example_river_possible_contamination
  - sensor.example_river_latest_discharge
  - sensor.example_river_latest_discharge_duration
  - sensor.example_river_estimated_contamination_until
  - sensor.example_river_estimated_contamination_remaining
```

For a richer single-card summary, a Markdown card can list every monitored outfall:

```yaml
type: markdown
title: Outfall details
content: |-
  {% set outfalls = state_attr('sensor.example_river_upstream_status', 'outfalls') or [] %}
  {% for outfall in outfalls %}
  **{{ outfall.site_id }} — {{ outfall.company }}**<br>
  {{ outfall.river or 'Unnamed watercourse' }} · {{ outfall.status }} ·
  {{ outfall.distance_km }} km away<br>
  Last discharge: {{ outfall.last_discharge or 'No recorded discharge' }}

  {% endfor %}
```

## Sewage Alerts UK custom card

The integration includes the dashboard card. Install or update the integration
and restart Home Assistant. In **Settings → Dashboards → Resources**, add
`/sewage_alerts_uk/sewage-alerts-uk-card.js` as a **JavaScript module**. If you
previously added a `/local/` copy of the card, edit that existing resource to
use the bundled URL. Reload the dashboard, choose **Add card → Sewage Alerts
UK**, and select a watch.

The card uses the watch's **Upstream status** sensor for both river and coastal
watches. Show or hide each section in the visual editor. You can also configure it
in YAML.

```yaml
type: custom:sewage-alerts-uk-card
entity: sensor.example_river_upstream_status
show:
  map: true
  warning: true
  countdown: true
  outfalls: false
```

The warning and countdown are on by default. The warning can stay visible after
all outfalls report inactive. During a discharge the card waits for a reported
end before showing a countdown.

Use the map's zoom buttons and select an outfall marker to see its details. The
blue line shows the saved upstream trace. Watches created before the integration
saved river geometry can still show their watch point and available outfall
locations. With the updated integration, use **Reconfigure** and enable **Search again for
monitored outfalls** to add the blue line to an existing river watch. The map requests OpenStreetMap tiles from the browser and displays the
watch data over the map as Home Assistant receives feed updates.

The map follows Home Assistant's
dark-mode setting. If the basemap cannot load, the card keeps showing the
available watch point, river trace and outfall markers.

The icon beside the watch title uses red for a reported discharge, yellow for
the precautionary window, green for no active discharge reported, and grey
when the status is unknown. Hover or tap for details. Outfall markers use
the same colours based on each site's report and latest reported end time.
The blue line shows the monitored river network. Marker colours describe
reports and precautionary timing. Water quality and downstream spread are
outside the scope of the feed.

Enable **Potential downstream paths** to show the shortest mapped routes from
outfalls to the watch point. Orange shows a reported discharge and yellow shows
a precautionary window. Orange takes priority where routes overlap. Tap a marker
to isolate its route, including inactive sites, and tap again to restore the
combined view. These routes show mapped connections rather than measured
pollution, and end at the watch point. Existing river watches can generate routes
with **Reconfigure → Search again for monitored outfalls**.
