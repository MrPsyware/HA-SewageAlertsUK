"""Opt-in public-data smoke test, never using the user's location."""

from unittest.mock import patch

import aiohttp
import pytest

from custom_components.sewage_alerts_uk.config_flow import SewageConfigFlow
from custom_components.sewage_alerts_uk.location import lookup_town


async def test_live_shrewsbury_discovery(hass, request):
    if not request.config.getoption("--run-live"):
        pytest.skip("Use --run-live to contact public APIs")
    async with aiohttp.ClientSession() as session:
        places = await lookup_town(session, "Shrewsbury")
        assert places
        flow = SewageConfigFlow()
        flow.hass, flow.context = hass, {"source": "user"}
        flow.location = places[0]
        with patch(
            "custom_components.sewage_alerts_uk.location_flow.async_get_clientsession",
            return_value=session,
        ):
            result = await flow._find_rivers()
            assert result is not None, flow.location_error
            assert result["step_id"] == "area"
            result = await flow.async_step_area({"area_type": "river"})
            assert result["step_id"] == "river"
            selected = next(
                snap
                for snap in flow.rivers.values()
                if "severn" in snap.link.name.lower()
            )
            result = await flow.async_step_river(
                {"river": selected.link.id, "upstream_km": 10}
            )
        assert result["step_id"] == "confirm", result.get("errors")
        assert flow.sites
        assert all(0 <= site["distance_m"] <= 10000 for site in flow.sites)
        print(
            f"\nShrewsbury: {len(flow.sites)} matched upstream outfalls on {flow.river_name}"
        )
