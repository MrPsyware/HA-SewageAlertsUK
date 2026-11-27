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
