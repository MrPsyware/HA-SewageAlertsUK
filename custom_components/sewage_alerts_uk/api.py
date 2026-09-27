"""Read the public Stream-compatible ArcGIS storm overflow feeds."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import aiohttp

from .const import STALE_AFTER


class FeedError(Exception):
    """The feed could not supply a trustworthy response."""


def timestamp(value: Any) -> datetime | None:
    """ArcGIS dates are UTC milliseconds since the epoch."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, UTC)
    except TypeError, ValueError, OverflowError, OSError:
        return None


@dataclass(frozen=True)
class Outfall:
    """One outfall, using the provider's stable ID, never ArcGIS OBJECTID."""

    site_id: str
    river: str
    company: str
    status: str
    latest_start: datetime | None
    latest_end: datetime | None
    updated: datetime | None
    latitude: float | None
    longitude: float | None

    def effective_status(self, now: datetime) -> str:
        if self.updated is None:
            return "unknown"
        if self.updated > now + STALE_AFTER:
            return "unknown"
        if now - self.updated > STALE_AFTER:
            return "stale"
        return self.status

    @property
    def label(self) -> str:
        return f"{self.river or 'Unnamed watercourse'} — {self.site_id}"


def coordinate(value: Any, limit: float) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) and abs(result) <= limit else None
    except TypeError, ValueError:
        return None


def parse_outfall(attributes: dict) -> Outfall:
    """Field casing differs between companies."""
    data = {key.lower(): value for key, value in attributes.items()}
    site_id = data.get("id")
    if site_id is None or not str(site_id).strip():
        raise FeedError("Feed record has no stable outfall ID")
    raw_status = data.get("status")
    status = {"1": "discharging", "0": "not_discharging", "-1": "offline"}.get(
        str(raw_status), "unknown"
    )
    return Outfall(
        site_id=str(site_id),
        river=str(data.get("receivingwatercourse") or ""),
        company=str(data.get("company") or ""),
        status=status,
        latest_start=timestamp(data.get("latesteventstart")),
        latest_end=timestamp(data.get("latesteventend")),
        updated=timestamp(data.get("lastupdated")),
        latitude=coordinate(data.get("latitude"), 90),
        longitude=coordinate(data.get("longitude"), 180),
    )


class StormOverflowClient:
    """Small asynchronous client; no authentication or scraped web pages."""

    def __init__(self, session: aiohttp.ClientSession, url: str) -> None:
        self.session = session
        self.url = url

    async def fetch(
        self, site_id: str | None = None, *, site_ids=None, center=None, radius=None
    ) -> dict[str, Outfall]:
        # IDs can contain quotes. Escape literals, never interpolate raw SQL.
        where = (
            "1=1" if site_id is None else "Id = '" + site_id.replace("'", "''") + "'"
        )
        if site_ids is not None:
            if not site_ids:
                return {}
            where = (
                "Id IN ("
                + ",".join("'" + value.replace("'", "''") + "'" for value in site_ids)
                + ")"
            )
        result: dict[str, Outfall] = {}
        offset = 0
        try:
            async with asyncio.timeout(60):
                for _ in range(100):
                    params = {
                        "f": "json",
                        "where": where,
                        "outFields": "*",
                        "returnGeometry": "false",
                        "resultOffset": str(offset),
                        "resultRecordCount": "1000",
                        "orderByFields": "Id ASC",
                    }
                    if center is not None:
                        latitude, longitude = center
                        params.update(
                            {
                                "geometry": f"{longitude},{latitude}",
                                "geometryType": "esriGeometryPoint",
                                "inSR": "4326",
                                "distance": str(radius),
                                "units": "esriSRUnit_Meter",
                                "spatialRel": "esriSpatialRelIntersects",
                            }
                        )
                    async with self.session.get(
                        self.url + "/query",
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        response.raise_for_status()
                        data = await response.json(content_type=None)
                    if not isinstance(data, dict) or "error" in data:
                        raise FeedError("ArcGIS returned an error response")
                    features = data.get("features")
                    if not isinstance(features, list):
                        raise FeedError("ArcGIS response is missing features")
                    for feature in features:
                        if not isinstance(feature, dict) or not isinstance(
                            feature.get("attributes"), dict
                        ):
                            raise FeedError("Invalid outfall record")
                        outfall = parse_outfall(feature["attributes"])
                        if outfall.site_id in result:
                            raise FeedError("Duplicate outfall ID or repeated page")
                        result[outfall.site_id] = outfall
                    if not data.get("exceededTransferLimit"):
                        return result
                    if not features:
                        raise FeedError("Feed pagination ended unexpectedly")
                    offset += len(features)
                raise FeedError("Feed pagination limit exceeded")
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise FeedError("Unable to read the storm overflow feed") from err
