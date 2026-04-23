"""Scraper de cartelera.cdmx.gob.mx — filtro por alcaldía Cuauhtémoc.

Usa los endpoints internos del plugin WordPress `cdmx-billboard`:
  - POST /api/v1/internal/events/search_builder       (eventos, paginado)
  - POST /api/v1/internal/events/search_builder       (lugares, paginado via by_venue_page)
  - POST /api/v1/internal/venue_info                  (detalle de lugar)
  - GET  /{event_id}/{dd-mm-yyyy}/x                   (detalle de evento: HTML con JSON embebido)

Salida:
  out/events.json      — eventos (resumen + detalle si --detail)
  out/venues.json      — lugares con dirección y lista de eventos
  out/events.csv       — CSV plano con columnas básicas
  out/venues.csv       — CSV plano con columnas básicas
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

BASE = "https://cartelera.cdmx.gob.mx"
API = f"{BASE}/api/v1/internal"
HOME = f"{BASE}/"
ZONE = "Cuauhtémoc"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

NONCE_RE = re.compile(
    r'name="ae-nonce-public-event-search"[^>]*value="([a-f0-9]+)"'
)
EVENT_INFO_RE = re.compile(
    r"var\s+cdmx_billboard_event_info\s*=\s*(\{.*?\});", re.DOTALL
)


def get_session() -> tuple[requests.Session, str]:
    """Crea sesión con cookies PHPSESSID y extrae el nonce de la home."""
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": UA,
            "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
        }
    )
    r = s.get(HOME, timeout=30)
    r.raise_for_status()
    m = NONCE_RE.search(r.text)
    if not m:
        raise RuntimeError("No se pudo extraer el nonce de la home")
    return s, m.group(1)


def base_form(nonce: str) -> dict[str, str]:
    return {
        "ae-nonce-public-event-search": nonce,
        "_wp_http_referer": "/",
        "by_language": "es",
        "by_nearest": "0",
        "by_nearest_zone": ZONE,
        "by_date": "",
    }


def post_multipart(
    s: requests.Session, url: str, fields: dict[str, str]
) -> dict[str, Any]:
    """POST multipart/form-data — la API lo requiere (FormData del navegador)."""
    files = {k: (None, v) for k, v in fields.items()}
    r = s.post(
        url,
        files=files,
        headers={"Referer": HOME, "Origin": BASE, "Accept": "application/json"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def fetch_events_page(
    s: requests.Session, nonce: str, page: int
) -> dict[str, Any]:
    fields = base_form(nonce) | {"by_event_page": str(page)}
    data = post_multipart(s, f"{API}/events/search_builder", fields)
    return data["data"]["event_data"]


def fetch_venues_page(
    s: requests.Session, nonce: str, page: int
) -> dict[str, Any]:
    fields = base_form(nonce) | {"by_venue_page": str(page)}
    data = post_multipart(s, f"{API}/events/search_builder", fields)
    return data["data"]["venue_data"]


def fetch_venue_info(
    s: requests.Session, nonce: str, venue_id: str
) -> dict[str, Any]:
    fields = base_form(nonce) | {"by_venue_id": str(venue_id)}
    data = post_multipart(s, f"{API}/venue_info", fields)
    return data["data"]


def fetch_event_detail(
    s: requests.Session, event_id: str, date_located: str
) -> dict[str, Any] | None:
    """Descarga la página HTML del evento y extrae el JSON embebido."""
    date_url = date_located.replace("/", "-")
    url = f"{BASE}/{event_id}/{date_url}/x"
    r = s.get(url, timeout=30, headers={"Referer": HOME})
    if r.status_code != 200:
        return None
    m = EVENT_INFO_RE.search(r.text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def scrape_events(
    s: requests.Session, nonce: str, with_detail: bool, sleep: float
) -> list[dict[str, Any]]:
    first = fetch_events_page(s, nonce, 1)
    total_pages = int(first.get("event_pages_total") or 1)
    total_items = int(first.get("event_items_total") or 0)
    print(f"[events] {total_items} eventos en {total_pages} páginas", file=sys.stderr)

    events: list[dict[str, Any]] = list(first.get("event_items_list") or [])
    for page in range(2, total_pages + 1):
        print(f"[events] página {page}/{total_pages}", file=sys.stderr)
        time.sleep(sleep)
        try:
            data = fetch_events_page(s, nonce, page)
            events.extend(data.get("event_items_list") or [])
        except Exception as e:
            print(f"[events] error página {page}: {e}", file=sys.stderr)

    if with_detail:
        for i, ev in enumerate(events, 1):
            print(
                f"[events] detalle {i}/{len(events)} id={ev['event_id']}",
                file=sys.stderr,
            )
            time.sleep(sleep)
            try:
                detail = fetch_event_detail(
                    s, ev["event_id"], ev.get("event_date_located", "")
                )
                if detail:
                    ev["detail"] = detail
            except Exception as e:
                print(f"[events] error detalle {ev['event_id']}: {e}", file=sys.stderr)
    return events


def scrape_venues(
    s: requests.Session, nonce: str, with_detail: bool, sleep: float
) -> list[dict[str, Any]]:
    first = fetch_venues_page(s, nonce, 1)
    total_pages = int(first.get("venue_pages_total") or 1)
    total_items = int(first.get("venue_items_total") or 0)
    print(f"[venues] {total_items} lugares en {total_pages} páginas", file=sys.stderr)

    venues: list[dict[str, Any]] = list(first.get("venue_items_list") or [])
    for page in range(2, total_pages + 1):
        print(f"[venues] página {page}/{total_pages}", file=sys.stderr)
        time.sleep(sleep)
        try:
            data = fetch_venues_page(s, nonce, page)
            venues.extend(data.get("venue_items_list") or [])
        except Exception as e:
            print(f"[venues] error página {page}: {e}", file=sys.stderr)

    if with_detail:
        for i, v in enumerate(venues, 1):
            print(
                f"[venues] info {i}/{len(venues)} id={v['venue_id']}",
                file=sys.stderr,
            )
            time.sleep(sleep)
            try:
                info = fetch_venue_info(s, nonce, v["venue_id"])
                v["venue_address"] = info.get("venue_info", {}).get("venue_address")
                v["events"] = info.get("venue_event_list", [])
            except Exception as e:
                print(f"[venues] error info {v['venue_id']}: {e}", file=sys.stderr)
    return venues


def write_csv(rows: list[dict[str, Any]], path: Path, columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent / "out",
        help="Directorio de salida (default: ./out)",
    )
    ap.add_argument(
        "--detail",
        action="store_true",
        help="Descarga detalle completo de cada evento y lugar (más lento)",
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=0.3,
        help="Pausa entre requests en segundos (default: 0.3)",
    )
    ap.add_argument(
        "--only",
        choices=["events", "venues", "all"],
        default="all",
    )
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    s, nonce = get_session()
    print(f"Nonce: {nonce}", file=sys.stderr)

    if args.only in ("events", "all"):
        events = scrape_events(s, nonce, args.detail, args.sleep)
        (args.out / "events.json").write_text(
            json.dumps(events, ensure_ascii=False, indent=2)
        )
        write_csv(
            events,
            args.out / "events.csv",
            [
                "event_id",
                "event_type",
                "event_name",
                "event_venue",
                "event_date_located",
                "event_lat",
                "event_lon",
                "event_thumb",
            ],
        )
        print(f"[events] guardados {len(events)} registros en {args.out}", file=sys.stderr)

    if args.only in ("venues", "all"):
        venues = scrape_venues(s, nonce, args.detail, args.sleep)
        (args.out / "venues.json").write_text(
            json.dumps(venues, ensure_ascii=False, indent=2)
        )
        write_csv(
            venues,
            args.out / "venues.csv",
            [
                "venue_id",
                "venue_name",
                "venue_address",
                "venue_lat",
                "venue_lon",
                "venue_event_total",
                "venue_image",
            ],
        )
        print(f"[venues] guardados {len(venues)} registros en {args.out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
