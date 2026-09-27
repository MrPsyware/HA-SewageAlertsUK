"""Exercise actual HA entity/flow classes and public feed response fixtures."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sewage_alerts_uk.api import (
    FeedError,
    StormOverflowClient,
    parse_outfall,
    timestamp,
)
from custom_components.sewage_alerts_uk.binary_sensor import DischargingSensor
from custom_components.sewage_alerts_uk.config_flow import SewageConfigFlow
from custom_components.sewage_alerts_uk.coordinator import SewageCoordinator
from custom_components.sewage_alerts_uk.sensor import SewageSensor

SAMPLES = json.loads(Path(__file__).with_name("feed_samples.json").read_text())
NOW = datetime.now(UTC)


@pytest.fixture
def outfall():
    return replace(parse_outfall(SAMPLES["severn_trent_water"]), updated=NOW)


def entry():
    return SimpleNamespace(
        title="Test river — SVT00001",
        entry_id="entry",
        async_on_unload=MagicMock(),
        data={
            "provider": "severn_trent_water",
            "site_id": "SVT00001",
            "company": "Severn Trent Water",
            "url": "https://example.test/0",
        },
    )


@pytest.mark.parametrize("provider", SAMPLES)
def test_real_feed_samples(provider):
    data = parse_outfall(SAMPLES[provider])
    assert data.site_id
    assert data.river
    assert data.status == "not_discharging"
    assert data.updated.tzinfo is UTC
    assert -90 <= data.latitude <= 90
    assert -180 <= data.longitude <= 180


@pytest.mark.parametrize(
    "raw, expected",
    [
        (1, "discharging"),
        (0, "not_discharging"),
        (-1, "offline"),
        (None, "unknown"),
        (7, "unknown"),
        (True, "unknown"),
    ],
)
def test_status_mapping(raw, expected):
    assert parse_outfall({"Id": "test", "Status": raw}).status == expected


@pytest.mark.parametrize(
    "value", [None, "invalid", float("nan"), float("inf"), 10**30, True]
)
def test_invalid_timestamps(value):
    assert timestamp(value) is None


def test_missing_id_is_not_silently_ignored():
    with pytest.raises(FeedError):
        parse_outfall({"Status": 0})


@pytest.mark.parametrize(
    "status, age, expected",
    [
        ("discharging", 0, True),
        ("not_discharging", 0, False),
        ("offline", 0, None),
        ("unknown", 0, None),
        ("not_discharging", 25, None),
        ("discharging", 25, None),
    ],
)
async def test_binary_never_reports_missing_data_as_clear(
    hass, outfall, status, age, expected
):
    coordinator = SimpleNamespace(
        hass=hass,
        site_id=outfall.site_id,
        last_update_success=True,
        data=replace(outfall, status=status, updated=NOW - timedelta(hours=age)),
    )
    sensor = DischargingSensor(coordinator, entry(), "discharging")
    assert sensor.is_on is expected
    assert sensor.available
    coordinator.last_update_success = False
    assert not sensor.available


async def test_status_and_timestamps(hass, outfall):
    coordinator = SimpleNamespace(
        hass=hass, site_id=outfall.site_id, last_update_success=True, data=outfall
    )
    status = SewageSensor(coordinator, entry(), "status", "Status")
    assert status.native_value == "not_discharging"
    coordinator.data = replace(outfall, updated=NOW - timedelta(days=2))
    assert status.native_value == "stale"
    coordinator.data = replace(outfall, updated=None)
    assert status.native_value == "unknown"
    started = SewageSensor(
        coordinator, entry(), "latest_start", "Latest discharge start"
    )
    assert started.native_value == outfall.latest_start
    assert started.unique_id != status.unique_id


def mock_session(*payloads):
    session = MagicMock()
    responses = []
    for payload in payloads:
        response = MagicMock()
        response.json = AsyncMock(return_value=payload)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        responses.append(context)
    session.get.side_effect = responses
    return session


async def test_pagination_and_escaping():
    session = mock_session(
        {
            "features": [{"attributes": {"Id": "A", "Status": 1}}],
            "exceededTransferLimit": True,
        },
        {"features": [{"attributes": {"Id": "B", "Status": 0}}]},
    )
    result = await StormOverflowClient(session, "https://example.test").fetch("A'B")
    assert set(result) == {"A", "B"}
    calls = session.get.call_args_list
    assert calls[0].kwargs["params"]["where"] == "Id = 'A''B'"
    assert calls[1].kwargs["params"]["resultOffset"] == "1"


@pytest.mark.parametrize(
    "payload",
    [
        {"error": {"code": 500}},
        {},
        [],
        {"features": [None]},
        {"features": [], "exceededTransferLimit": True},
    ],
)
async def test_bad_responses(payload):
    with pytest.raises(FeedError):
        await StormOverflowClient(mock_session(payload), "https://example.test").fetch()


async def test_timeout():
    session = MagicMock()
    session.get.side_effect = TimeoutError
    with pytest.raises(FeedError):
        await StormOverflowClient(session, "https://example.test").fetch()


async def test_coordinator_missing_site_and_recovery(hass, outfall):
    with patch(
        "custom_components.sewage_alerts_uk.coordinator.async_get_clientsession"
    ):
        coordinator = SewageCoordinator(hass, entry())
    coordinator.client.fetch = AsyncMock(return_value={})
    with pytest.raises(UpdateFailed, match="missing"):
        await coordinator._async_update_data()
    coordinator.client.fetch.return_value = {"SVT00001": outfall}
    assert await coordinator._async_update_data() == outfall


async def test_flow_search_and_selection(hass, outfall):
    flow = SewageConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    result = await flow.async_step_manual()
    assert result["step_id"] == "manual"
    with (
        patch("custom_components.sewage_alerts_uk.config_flow.async_get_clientsession"),
        patch.object(
            StormOverflowClient,
            "fetch",
            AsyncMock(return_value={outfall.site_id: outfall}),
        ),
    ):
        result = await flow.async_step_manual(
            {"provider": "severn_trent_water", "search": " REA "}
        )
    assert result["step_id"] == "site"
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    result = await flow.async_step_site({"site_id": outfall.site_id})
    assert result["data"]["site_id"] == outfall.site_id
    flow.async_set_unique_id.assert_awaited_once_with("severn_trent_water_SVT00001")
    flow._abort_if_unique_id_configured.assert_called_once()


@pytest.mark.parametrize(
    "response, expected", [({}, "no_results"), (FeedError("failed"), "cannot_connect")]
)
async def test_flow_errors(hass, response, expected):
    flow = SewageConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    fetch = (
        AsyncMock(side_effect=response)
        if isinstance(response, Exception)
        else AsyncMock(return_value=response)
    )
    with (
        patch("custom_components.sewage_alerts_uk.config_flow.async_get_clientsession"),
        patch.object(StormOverflowClient, "fetch", fetch),
    ):
        result = await flow.async_step_manual(
            {"provider": "severn_trent_water", "search": "river"}
        )
    assert result["errors"]["base"] == expected
