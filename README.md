# Scraper Cartelera CDMX — Alcaldía Cuauhtémoc

Extrae eventos y lugares de <https://cartelera.cdmx.gob.mx> filtrados por la alcaldía **Cuauhtémoc** usando los endpoints internos del plugin WordPress `cdmx-billboard`, evitando renderizar la página pesada.

## Endpoints descubiertos

Todos son `POST` con `multipart/form-data` (FormData del navegador).

| Uso | Endpoint | Campos clave |
| --- | --- | --- |
| Listar eventos (paginado) | `/api/v1/internal/events/search_builder` | `by_nearest_zone=Cuauhtémoc`, `by_event_page=N` |
| Listar lugares (paginado) | `/api/v1/internal/events/search_builder` | `by_nearest_zone=Cuauhtémoc`, `by_venue_page=N` |
| Detalle de lugar | `/api/v1/internal/venue_info` | `by_venue_id=ID` |
| Detalle de evento (HTML) | `GET /{event_id}/{dd-mm-yyyy}/x` | JSON embebido en `var cdmx_billboard_event_info` |

Campos comunes de todas las peticiones POST:

```
ae-nonce-public-event-search   (se extrae de la home)
_wp_http_referer=/
by_language=es
by_nearest=0
by_nearest_zone=Cuauhtémoc
```

El servidor no valida estrictamente el nonce para estos endpoints, pero mantenerlo + la cookie `PHPSESSID` de la sesión evita respuestas vacías.

## Paginación

- Eventos: 9 por página, campo `event_pages_total` en la respuesta.
- Lugares: 9 por página, campo `venue_pages_total` en la respuesta.

## Uso

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install requests

# Listado básico (rápido)
python scraper.py

# Con detalle completo de cada evento y dirección de cada lugar (lento)
python scraper.py --detail --sleep 0.5

# Solo lugares
python scraper.py --only venues --detail
```

Salidas en `./out/`:

- `events.json` — lista completa con todos los campos devueltos por la API (+ `detail` si `--detail`).
- `events.csv` — columnas planas (id, tipo, nombre, lugar, fecha, lat, lon, thumb).
- `venues.json` — lista de lugares con `venue_address` y `events` si `--detail`.
- `venues.csv` — columnas planas.

## Notas

- El script respeta pausas (`--sleep`) entre peticiones para no saturar el servidor.
- Los eventos traen `event_date_located` en formato `dd/mm/yyyy`; para construir la URL de detalle se reemplaza `/` por `-`.
- La slug del URL de detalle puede ser cualquier string no vacío (se usa `x`).
