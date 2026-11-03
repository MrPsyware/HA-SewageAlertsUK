"""Directed OS Open Rivers tracing in a local metre projection.

Only connected, non-tidal inland links with explicit flow direction are traced.
Distance is measured along polylines, not as a radius or compass bearing.
"""

import heapq
import math
from collections import defaultdict
from dataclasses import dataclass
from itertools import pairwise

from .api import FeedError

RIVER_URL = "https://services.arcgis.com/qHLhLQrcvEnxjtPr/arcgis/rest/services/OS_OpenRivers/FeatureServer/0"
METRES_PER_DEGREE = math.pi * 6371008.8 / 180
SNAP_METRES = 100


@dataclass
class Link:
    id: str
    name: str
    start: str
    end: str
    points: list[tuple[float, float]]
    length: float
    bounds: tuple[float, float, float, float]
    routable: bool
    form: str


@dataclass
class Snap:
    link: Link
    offset: float  # Metres downstream from the start node.
    distance: float
    point: tuple[float, float]


class RiverNetwork:
    def __init__(self, features, latitude, longitude):
        self.latitude, self.longitude = latitude, longitude
        self.x_scale = METRES_PER_DEGREE * math.cos(math.radians(latitude))
        self.links = {}
        self.incoming = defaultdict(list)
        for feature in features:
            try:
                attrs = feature["attributes"]
                paths = feature["geometry"]["paths"]
                if len(paths) != 1 or len(paths[0]) < 2:
                    raise FeedError("Unsupported river geometry")
                points = [self.project(p[1], p[0]) for p in paths[0]]
                start, end = attrs["startNode"], attrs["endNode"]
                flow = str(attrs.get("flow", "")).replace(" ", "").lower()
                if flow == "indirection":
                    known_direction = True
                elif flow == "oppositedirection":
                    points.reverse()
                    start, end = end, start
                    known_direction = True
                else:
                    known_direction = False
                xs, ys = zip(*points)
                names = list(
                    dict.fromkeys(
                        str(attrs.get(key) or "").strip() for key in ("name1", "name2")
                    )
                )
                link = Link(
                    str(attrs["identifier"]),
                    " / ".join(name for name in names if name) or "Unnamed watercourse",
                    start,
                    end,
                    points,
                    sum(math.dist(a, b) for a, b in pairwise(points)),
                    (min(xs), min(ys), max(xs), max(ys)),
                    known_direction
                    and attrs.get("form") in ("inlandRiver", "lake")
                    and bool(start and end),
                    attrs.get("form", ""),
                )
                if link.id in self.links:
                    raise FeedError("Duplicate river link")
                self.links[link.id] = link
                if link.routable:
                    self.incoming[end].append(link)
            except (KeyError, TypeError, ValueError, IndexError) as err:
                raise FeedError("Invalid river network response") from err

    def project(self, latitude, longitude):
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            raise ValueError("Invalid coordinate")
        return (
            (longitude - self.longitude) * self.x_scale,
            (latitude - self.latitude) * METRES_PER_DEGREE,
        )

    def unproject(self, point):
        x, y = point
        return self.latitude + y / METRES_PER_DEGREE, self.longitude + x / self.x_scale

    def snap(self, link, point):
        best = None
        travelled = 0.0
        for a, b in pairwise(link.points):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            fraction = (
                0
                if not length
                else max(
                    0,
                    min(
                        1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length**2
                    ),
                )
            )
            projection = (a[0] + fraction * dx, a[1] + fraction * dy)
            distance = math.dist(point, projection)
            if best is None or distance < best.distance:
                best = Snap(link, travelled + fraction * length, distance, projection)
            travelled += length
        return best

    def nearest(self, latitude, longitude, limit=1, maximum=5000):
        point = self.project(latitude, longitude)
        candidates = []
        for link in self.links.values():
            left, bottom, right, top = link.bounds
            bound = math.hypot(
                max(left - point[0], 0, point[0] - right),
                max(bottom - point[1], 0, point[1] - top),
            )
            if bound > maximum:
                continue
            snap = self.snap(link, point)
            if snap.distance <= maximum:
                candidates.append(snap)
        return sorted(candidates, key=lambda snap: (snap.distance, snap.link.id))[
            :limit
        ]

    def upstream(self, target: Snap, maximum: float):
        """Map link IDs to distance from their downstream end to the target."""
        if not target.link.routable:
            raise FeedError("Selected watercourse has no supported flow direction")
        # A negative end-distance clips the part downstream of the target.
        ends = {target.link.id: target.offset - target.link.length}
        queue = [(target.offset, target.link.start)]
        visited = {}
        while queue:
            distance, node = heapq.heappop(queue)
            if distance > maximum or distance >= visited.get(node, math.inf):
                continue
            visited[node] = distance
            for link in self.incoming[node]:
                if (
                    link.id == target.link.id
                ):  # Do not loop round a cycle to the target.
                    continue
                if distance < ends.get(link.id, math.inf):
                    ends[link.id] = distance
                    heapq.heappush(queue, (distance + link.length, link.start))
        return ends

    def match_outfalls(self, outfalls, target, maximum):
        ends = self.upstream(target, maximum)
        matches = {}
        for key, outfall in outfalls.items():
            if outfall.latitude is None or outfall.longitude is None:
                continue
            # Snap against ALL nearby links, not just upstream ones: otherwise
            # a downstream or neighbouring-river outfall could be pulled upstream.
            snaps = self.nearest(
                outfall.latitude, outfall.longitude, limit=2, maximum=SNAP_METRES
            )
            if not snaps:
                continue
            closest = snaps[0]
            if len(snaps) > 1 and snaps[1].distance - closest.distance < 10:
                # Ambiguous association near parallel rivers or confluences.
                continue
            if closest.link.id not in ends:
                continue
            distance = ends[closest.link.id] + closest.link.length - closest.offset
            if 0 <= distance <= maximum:
                matches[key] = round(distance, 1)
        return matches
