"""Test topology, partial river segments, discovery and conservative aggregation."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from test_integration import mock_session

from custom_components.sewage_alerts_uk.api import FeedError, parse_outfall
from custom_components.sewage_alerts_uk.config_flow import SewageConfigFlow
from custom_components.sewage_alerts_uk.location import (
    lookup_postcode,
    lookup_town,
    river_features,
)
from custom_components.sewage_alerts_uk.river import METRES_PER_DEGREE, RiverNetwork
from custom_components.sewage_alerts_uk.watch import WatchCoordinator, WatchState


def feature(identifier, start, end, points, **attributes):
    # Coordinates near 52N in metres for easy assertions.
    import math

    scale = METRES_PER_DEGREE * math.cos(math.radians(52))
    return {
        "attributes": {
            "identifier": identifier,
            "startNode": start,
            "endNode": end,
            "name1": identifier,
            "flow": "in direction",
            "form": "inlandRiver",
            **attributes,
        },
        "geometry": {
            "paths": [[[x / scale, 52 + y / METRES_PER_DEGREE] for x, y in points]]
        },
    }


@pytest.fixture
def network():
    return RiverNetwork(
        [
            feature("main", "B", "C", [(0, 0), (1000, 0)]),
            feature("upper", "A", "B", [(-1000, 0), (0, 0)]),
            feature("tributary", "T", "B", [(-1000, 1000), (0, 0)]),
            feature("other", "X", "Y", [(-1000, 200), (1000, 200)]),
            feature("downstream", "C", "D", [(1000, 0), (2000, 0)]),
        ],
        52,
        0,
    )


def outfall(network, x, y, status=0):
    latitude, longitude = network.unproject((x, y))
    return parse_outfall(
        {
            "Id": f"{x}:{y}",
            "Latitude": latitude,
            "Longitude": longitude,
            "Status": status,
            "LastUpdated": datetime.now(UTC).timestamp() * 1000,
        }
    )


def test_upstream_clips_target_segment_and_excludes_other_rivers(network):
    target = network.snap(network.links["main"], (500, 0))
    records = {
        "up": outfall(network, 200, 0),
        "down": outfall(network, 800, 0),
        "tributary": outfall(network, -500, 500),
        "other": outfall(network, 200, 200),
        "too_far": outfall(network, -900, 0),
        "off_network": outfall(network, -500, -300),
    }
    matches = network.match_outfalls(records, target, 1250)
    assert set(matches) == {"up", "tributary"}
    assert matches["up"] == pytest.approx(300, abs=0.1)
    assert matches["tributary"] == pytest.approx(500 + 500 * 2**0.5, abs=0.1)


def test_range_is_along_bends_not_straight_line():
    network = RiverNetwork(
        [feature("bend", "A", "B", [(0, 0), (0, 1000), (1000, 1000), (1000, 0)])], 52, 0
    )
    target = network.snap(network.links["bend"], (1000, 0))
    assert network.match_outfalls({"a": outfall(network, 0, 0)}, target, 1500) == {}
    assert network.match_outfalls({"a": outfall(network, 0, 0)}, target, 3500)[
        "a"
    ] == pytest.approx(3000, abs=0.1)


def test_ambiguous_confluence_is_not_assumed(network):
    target = network.snap(network.links["main"], (500, 0))
    assert network.match_outfalls({"a": outfall(network, 0, 0)}, target, 1000) == {}


def test_unknown_flow_and_tidal_links_not_routed():
    network = RiverNetwork(
        [
            feature("unknown", "A", "B", [(0, 0), (100, 0)], flow="unknown"),
            feature("tidal", "B", "C", [(100, 0), (200, 0)], form="tidalRiver"),
            feature("canal", "D", "E", [(300, 0), (400, 0)], form="canal"),
        ],
        52,
        0,
    )
    for link in network.links.values():
        assert not link.routable
        with pytest.raises(FeedError):
            network.upstream(network.snap(link, link.points[0]), 1000)


def test_connected_lake_links_and_bilingual_names():
    network = RiverNetwork(
        [
            feature("upper", "A", "B", [(0, 0), (100, 0)]),
            feature("lake", "B", "C", [(100, 0), (200, 0)], form="lake"),
            feature(
                "lower",
                "C",
                "D",
                [(200, 0), (300, 0)],
                name1="Afon Hafren",
                name2="River Severn",
            ),
        ],
        52,
        0,
    )
    target = network.snap(network.links["lower"], (250, 0))
    assert set(network.upstream(target, 1000)) == {"lower", "lake", "upper"}
    assert network.links["lower"].name == "Afon Hafren / River Severn"


def test_cycles_terminate_and_reverse_flow():
    network = RiverNetwork(
        [
            feature("a", "A", "B", [(0, 0), (100, 0)]),
            feature("b", "B", "A", [(100, 0), (0, 0)]),
            feature(
                "reverse", "C", "B", [(200, 0), (100, 0)], flow="opposite direction"
            ),
        ],
        52,
        0,
    )
    assert network.links["reverse"].start == "B"
    assert network.links["reverse"].points[0][0] == pytest.approx(100)
    assert len(network.upstream(network.snap(network.links["a"], (50, 0)), 10000)) == 2


@pytest.mark.parametrize(
    "statuses, expected",
    [
        ([0, 0], False),
        ([0, -1], None),
        ([1, -1], True),
        ([1, 0], True),
        ([None, 0], None),
        ([], None),
    ],
)
def test_watch_never_claims_clear_with_missing_data(network, statuses, expected):
    state = WatchState(
        {
            str(i): outfall(network, 0, 0, status) if status is not None else None
            for i, status in enumerate(statuses)
        },
        [],
    )
    assert state.discharging(datetime.now(UTC)) is expected


def test_stale_watch_data(network):
    record = replace(
        outfall(network, 0, 0), updated=datetime.now(UTC) - timedelta(days=2)
    )
    state = WatchState({"a": record}, [])
    assert state.counts(datetime.now(UTC)) == (0, 1)
    assert state.discharging(datetime.now(UTC)) is None


async def test_geocoding():
    session = mock_session(
        {"result": {"postcode": "SY1 1AA", "latitude": 52.7, "longitude": -2.75}}
    )
    assert (await lookup_postcode(session, "SY1 1AA"))[0]["latitude"] == 52.7
    session = mock_session(
        {
            "result": [
                {
                    "name_1": "Newport",
                    "county_unitary": "Shropshire",
                    "latitude": 52.7,
                    "longitude": -2.3,
                },
                {
                    "name_1": "Newport",
                    "county_unitary": "Wales",
                    "latitude": 51.6,
                    "longitude": -3.0,
                },
            ]
        }
    )
    results = await lookup_town(session, "Newport")
    assert len(results) == 2
    assert results[0]["label"] != results[1]["label"]
    assert await lookup_postcode(mock_session({"result": None}), "INVALID") == []


async def test_river_pagination():
    session = mock_session(
        {"features": [{"id": 1}], "exceededTransferLimit": True},
        {"features": [{"id": 2}]},
    )
    assert len(await river_features(session, 52, 0, 1000)) == 2
    assert session.get.call_args_list[1].kwargs["params"]["resultOffset"] == "1"
    with pytest.raises(FeedError):
        await river_features(
            mock_session({"features": [], "exceededTransferLimit": True}), 52, 0, 1000
        )


async def test_location_menu_and_coordinates(hass, network):
    flow = SewageConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    result = await flow.async_step_user()
    assert set(result["menu_options"]) == {
        "home",
        "postcode",
        "town",
        "coordinates",
        "manual",
    }
    with (
        patch(
            "custom_components.sewage_alerts_uk.location_flow.async_get_clientsession"
        ),
        patch(
            "custom_components.sewage_alerts_uk.location_flow.load_network",
            AsyncMock(return_value=network),
        ),
    ):
        result = await flow.async_step_coordinates({"latitude": 52, "longitude": 0})
    assert result["step_id"] == "river"
    assert (
        result["data_schema"]({"river": "main", "upstream_km": 10})["upstream_km"] == 10
    )


async def test_location_confirm_preserves_watch_and_unique_id(hass):
    flow = SewageConfigFlow()
    flow.hass, flow.context = hass, {"source": "user"}
    flow.target_coords, flow.range_km, flow.river_name = (52.7, -2.75), 10, "Severn"
    flow.sites = [
        {"site_id": "S1", "company": "Water", "river": "Severn", "distance_m": 1000}
    ]
    flow.async_set_unique_id, flow._abort_if_unique_id_configured = (
        AsyncMock(),
        MagicMock(),
    )
    result = await flow.async_step_confirm()
    assert "1.00 km upstream" in result["description_placeholders"]["outfalls"]
    result = await flow.async_step_confirm({})
    assert result["data"]["mode"] == "upstream"
    assert result["data"]["sites"] == flow.sites
    assert result["data"]["upstream_km"] == 10


async def test_watch_partial_provider_failure(hass, network):
    sites = [
        {"provider": "a", "site_id": "1", "company": "A", "url": "https://a"},
        {"provider": "b", "site_id": "2", "company": "B", "url": "https://b"},
    ]
    entry = SimpleNamespace(data={"sites": sites}, async_on_unload=MagicMock())
    with patch("custom_components.sewage_alerts_uk.watch.async_get_clientsession"):
        coordinator = WatchCoordinator(hass, entry)
    with patch(
        "custom_components.sewage_alerts_uk.watch.StormOverflowClient.fetch",
        AsyncMock(side_effect=[{"1": outfall(network, 0, 0)}, FeedError("offline")]),
    ):
        state = await coordinator._async_update_data()
    assert state.failed_companies == ["B"]
    assert state.records["b:2"] is None
    assert state.discharging(datetime.now(UTC)) is None


async def test_discovery_does_not_silently_ignore_failed_company(hass, network):
    flow = SewageConfigFlow()
    flow.hass = hass
    flow.providers = {
        "a": {"name": "A", "url": "https://a"},
        "b": {"name": "B", "url": "https://b"},
    }
    flow.target_coords, flow.range_km = (52, 0), 10
    with (
        patch(
            "custom_components.sewage_alerts_uk.location_flow.async_get_clientsession"
        ),
        patch(
            "custom_components.sewage_alerts_uk.location_flow.load_network",
            AsyncMock(return_value=network),
        ),
        patch(
            "custom_components.sewage_alerts_uk.location_flow.StormOverflowClient.fetch",
            AsyncMock(side_effect=[{}, FeedError("offline")]),
        ),
        pytest.raises(FeedError, match="incomplete"),
    ):
        await flow._discover_upstream("main")
