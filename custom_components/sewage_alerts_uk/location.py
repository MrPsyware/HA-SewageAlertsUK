"""Location lookup and bounded spatial river queries used during setup only."""

import asyncio
from urllib.parse import quote

import aiohttp

from .api import FeedError, coordinate
from .river import RIVER_URL, RiverNetwork


async def get_json(session, url, params=None):
    try:
        async with session.get(
            url, params=params, timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status == 404:
                return {"result": None}
            response.raise_for_status()
            data = await response.json(content_type=None)
        if not isinstance(data, dict) or "error" in data:
            raise FeedError("Location or river service returned an error")
        return data
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise FeedError("Unable to read location or river data") from err


def location_result(record, label):
    latitude = coordinate(record.get("latitude"), 90)
    longitude = coordinate(record.get("longitude"), 180)
    if latitude is None or longitude is None:
        raise FeedError("Location has no valid coordinates")
    return {"label": label, "latitude": latitude, "longitude": longitude}


async def lookup_postcode(session, postcode):
    data = await get_json(
        session,
        "https://api.postcodes.io/postcodes/" + quote(postcode.strip(), safe=""),
    )
    record = data.get("result")
    if not record:
        return []
    return [location_result(record, record["postcode"])]


async def lookup_town(session, town):
    data = await get_json(
        session, "https://api.postcodes.io/places", {"q": town.strip(), "limit": "10"}
    )
    return [
        location_result(
            record,
            ", ".join(
                filter(
                    None,
                    [
                        record["name_1"],
                        record.get("county_unitary"),
                        record.get("country"),
                    ],
                )
            ),
        )
        for record in (data.get("result") or [])
    ]


async def river_features(session, latitude, longitude, radius):
    features = []
    async with asyncio.timeout(120):
        for _ in range(20):
            data = await get_json(
                session,
                RIVER_URL + "/query",
                {
                    "f": "json",
                    "where": "1=1",
                    "outFields": "*",
                    "outSR": "4326",
                    "geometry": f"{longitude},{latitude}",
                    "geometryType": "esriGeometryPoint",
                    "inSR": "4326",
                    "distance": str(radius),
                    "units": "esriSRUnit_Meter",
                    "spatialRel": "esriSpatialRelIntersects",
                    "returnGeometry": "true",
                    "orderByFields": "OBJECTID ASC",
                    "resultOffset": str(len(features)),
                    "resultRecordCount": "2000",
                },
            )
            page = data.get("features")
            if not isinstance(page, list):
                raise FeedError("River response is missing features")
            features.extend(page)
            if not data.get("exceededTransferLimit"):
                return features
            if not page:
                break
    raise FeedError("River network query is incomplete; reduce the range")


async def load_network(hass, session, latitude, longitude, radius):
    try:
        features = await river_features(session, latitude, longitude, radius)
    except TimeoutError as err:
        raise FeedError("River network query timed out") from err
    return await hass.async_add_executor_job(
        RiverNetwork, features, latitude, longitude
    )
