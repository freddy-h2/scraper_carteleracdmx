"""Scrape cartelera.cdmx.gob.mx (Cuauhtémoc) y hace upsert directo a Supabase.

Reusa scraper.py y escribe a las tablas `public.cartelera_venues` y
`public.cartelera_events` (migration 0013). Idempotente: re-ejecutar sólo
actualiza filas por PK.

Variables de entorno requeridas:
  SUPABASE_URL           https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY   JWT con rol service_role (bypass RLS)

Opcionales:
  SCRAPER_SLEEP=0.5      pausa entre requests a cartelera.cdmx
  SCRAPER_DETAIL=1       1=incluye detalle por evento/lugar (default), 0=rápido
  UPSERT_BATCH=500       filas por request a PostgREST
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

import requests

from scraper import get_session, scrape_events, scrape_venues

VENUE_COLS = [
    "venue_id",
    "venue_name",
    "venue_address",
    "venue_lat",
    "venue_lon",
    "venue_event_total",
    "venue_image",
]
EVENT_COLS = [
    "event_id",
    "event_type",
    "event_name",
    "event_venue",
    "event_date_located",
    "event_lat",
    "event_lon",
    "event_thumb",
]
NUMERIC_COLS = {"venue_lat", "venue_lon", "event_lat", "event_lon"}
INT_COLS = {"venue_event_total"}


def _project(row: dict[str, Any], cols: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for c in cols:
        v = row.get(c)
        if v == "":
            v = None
        if c in INT_COLS and v is not None:
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = None
        # NUMERIC columns: PostgREST acepta string "19.432602" y lo castea.
        out[c] = v
    return out


def _upsert(
    url: str,
    key: str,
    table: str,
    rows: list[dict[str, Any]],
    conflict_col: str,
    batch: int,
) -> None:
    if not rows:
        print(f"[{table}] nada que upsertar", file=sys.stderr)
        return
    endpoint = f"{url}/rest/v1/{table}?on_conflict={conflict_col}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        r = requests.post(endpoint, headers=headers, json=chunk, timeout=60)
        if r.status_code >= 400:
            print(
                f"[{table}] HTTP {r.status_code}: {r.text[:500]}",
                file=sys.stderr,
            )
            r.raise_for_status()
        print(
            f"[{table}] upsert {i + len(chunk)}/{len(rows)}",
            file=sys.stderr,
        )


def main() -> int:
    try:
        url = os.environ["SUPABASE_URL"].rstrip("/")
        key = os.environ["SUPABASE_SERVICE_KEY"]
    except KeyError as e:
        print(f"Falta variable de entorno: {e}", file=sys.stderr)
        return 2

    sleep = float(os.environ.get("SCRAPER_SLEEP", "0.5"))
    detail = os.environ.get("SCRAPER_DETAIL", "1") != "0"
    batch = int(os.environ.get("UPSERT_BATCH", "500"))

    started = time.time()
    print(
        f"[ingest] inicio sleep={sleep} detail={detail} batch={batch}",
        file=sys.stderr,
    )

    s, nonce = get_session()

    venues = scrape_venues(s, nonce, detail, sleep)
    events = scrape_events(s, nonce, detail, sleep)

    v_rows = [_project(v, VENUE_COLS) for v in venues]
    e_rows = [_project(e, EVENT_COLS) for e in events]

    _upsert(url, key, "cartelera_venues", v_rows, "venue_id", batch)
    _upsert(url, key, "cartelera_events", e_rows, "event_id", batch)

    elapsed = time.time() - started
    print(
        f"[ingest] OK {len(v_rows)} venues, {len(e_rows)} events "
        f"en {elapsed:.1f}s",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
