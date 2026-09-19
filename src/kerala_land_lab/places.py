"""Optional, uncached Google Places Nearby Search integration."""
from __future__ import annotations

import os
import requests

PLACE_TYPES = ["hospital", "pharmacy", "school", "supermarket", "bank"]


def nearby_places(lon: float, lat: float, radius_m: int = 3000) -> list[dict]:
    """Return a small live result set; callers must display Google Maps attribution."""
    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not key:
        return []
    response = requests.post(
        "https://places.googleapis.com/v1/places:searchNearby",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": "places.id,places.displayName,places.primaryType,places.location,places.googleMapsUri",
        },
        json={
            "includedTypes": PLACE_TYPES,
            "maxResultCount": 10,
            "rankPreference": "DISTANCE",
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": min(max(radius_m, 500), 5000),
                }
            },
        },
        timeout=(10, 20),
    )
    response.raise_for_status()
    places = []
    for item in response.json().get("places", []):
        location = item.get("location", {})
        places.append(
            {
                "place_id": item.get("id"),
                "name": item.get("displayName", {}).get("text", "Unnamed place"),
                "kind": item.get("primaryType", "place").replace("_", " "),
                "lat": location.get("latitude"),
                "lon": location.get("longitude"),
                "google_maps_uri": item.get("googleMapsUri"),
                "source": "Google Maps",
            }
        )
    return places
