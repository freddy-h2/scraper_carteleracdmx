"""Transforma out/{events,venues}.json a CSVs con los headers que espera
la tabla public.events / public.places de la migration 0011.

Uso:
    python transform_for_supabase.py

Genera en ./out/:
    places_supabase.csv
    events_supabase.csv

Orden de importación en Supabase:
    1. Importar places_supabase.csv → tabla public.places.
    2. Importar events_supabase.csv → tabla public.events.
    3. Correr link_events_to_places.sql para poblar events.place_id
       usando el array de event_ids guardado en places.metadata.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

OUT = Path(__file__).parent / "out"
SOURCE = "cartelera_cdmx"
DEPARTMENT = "cultura"
# CDMX no observa horario de verano desde 2022 → siempre UTC-6.
TZ_OFFSET = "-06:00"


def to_iso_date(d: str) -> str:
    """'24/04/2026' → '2026-04-24 00:00:00-06:00' (Postgres timestamptz)."""
    dd, mm, yyyy = d.split("/")
    return f"{yyyy}-{mm}-{dd} 00:00:00{TZ_OFFSET}"


def transform_places() -> None:
    venues = json.loads((OUT / "venues.json").read_text())
    path = OUT / "places_supabase.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "source",
                "source_id",
                "name",
                "address",
                "latitude",
                "longitude",
                "department",
                "image_url",
                "metadata",
            ]
        )
        for v in venues:
            # venue_event_list viene como CSV "11062,12209,14296,…"
            raw_list = v.get("venue_event_list") or ""
            event_ids = [e.strip() for e in raw_list.split(",") if e.strip()]
            metadata = {
                "event_ids": event_ids,
                "event_total": int(v.get("venue_event_total") or 0),
            }
            w.writerow(
                [
                    SOURCE,
                    v["venue_id"],
                    v["venue_name"],
                    v.get("venue_address") or "",
                    v.get("venue_lat") or "",
                    v.get("venue_lon") or "",
                    DEPARTMENT,
                    v.get("venue_image") or "",
                    json.dumps(metadata, ensure_ascii=False),
                ]
            )
    print(f"Escrito {path} ({len(venues)} lugares)")


def transform_events() -> None:
    events = json.loads((OUT / "events.json").read_text())
    path = OUT / "events_supabase.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "source",
                "source_id",
                "title",
                "starts_at",
                "category",
                "location_text",
                "image_url",
                "department",
                "metadata",
            ]
        )
        for e in events:
            metadata = {
                "event_lat": e.get("event_lat"),
                "event_lon": e.get("event_lon"),
                "source_venue_name": e.get("event_venue"),
            }
            w.writerow(
                [
                    SOURCE,
                    e["event_id"],
                    e["event_name"],
                    to_iso_date(e["event_date_located"]),
                    e.get("event_type") or "",
                    e.get("event_venue") or "",
                    e.get("event_thumb") or "",
                    DEPARTMENT,
                    json.dumps(metadata, ensure_ascii=False),
                ]
            )
    print(f"Escrito {path} ({len(events)} eventos)")


if __name__ == "__main__":
    transform_places()
    transform_events()
