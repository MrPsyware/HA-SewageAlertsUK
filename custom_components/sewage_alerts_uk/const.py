"""Constants for Sewage Alerts UK."""

from datetime import timedelta

DOMAIN = "sewage_alerts_uk"
CONF_PROVIDER = "provider"
CONF_SITE_ID = "site_id"
POLL_INTERVAL = timedelta(minutes=15)
STALE_AFTER = timedelta(hours=24)
ATTRIBUTION = "Data from water companies via the Stream National Storm Overflow Hub"
