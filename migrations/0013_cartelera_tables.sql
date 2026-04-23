-- 0013: tablas públicas con el esquema exacto de out/events.csv y out/venues.csv
--
-- WHY: el importador CSV de Supabase exige que los headers del archivo
-- coincidan 1:1 con los nombres de columna de la tabla destino. Esta
-- migration crea dos tablas cuyos nombres y tipos replican las columnas
-- que produce el scraper (scraper.py → out/events.csv, out/venues.csv),
-- de modo que se pueden subir desde el dashboard sin transformación.
--
-- DECISIONES DE TIPO
-- - event_id / venue_id: TEXT + PRIMARY KEY. Son strings numéricos en la
--   API ("37203"); mantenerlos como text evita casts y permite futuros
--   IDs no numéricos.
-- - event_date_located: TEXT. La API devuelve "dd/mm/yyyy" que Postgres
--   no parsea como DATE por default (DateStyle='ISO'). Guardar como texto
--   permite que el CSV cargue directo; se puede añadir una columna
--   generada `event_date date GENERATED ALWAYS AS (to_date(...)) STORED`
--   después si se necesita filtrar por rango.
-- - lat/lon: NUMERIC(9,6). Casts limpios desde strings "19.432602".
-- - venue_event_total: INTEGER.
--
-- RLS: mismo patrón que public.knowledge (migration 0008). RLS on,
-- cero políticas → service_role bypassa, anon/authenticated no ven nada.
--
-- Cómo aplicar:
--   psql "$DATABASE_URL" -f scraper_carteleracdmx/migrations/0013_cartelera_tables.sql
-- o:
--   supabase db push
--
-- Idempotente: seguro re-ejecutar.

begin;

-- ===========================================================================
-- 1. TABLA public.cartelera_venues
-- ===========================================================================
--
-- Lugares extraídos de cartelera.cdmx.gob.mx (alcaldía Cuauhtémoc).
-- Esquema idéntico a los headers de out/venues.csv.

create table if not exists public.cartelera_venues (
  venue_id           text primary key,
  venue_name         text not null,
  venue_address      text,
  venue_lat          numeric(9, 6),
  venue_lon          numeric(9, 6),
  venue_event_total  integer,
  venue_image        text,
  -- Campos operativos con default → ausentes en el CSV, Postgres los llena.
  active             boolean     not null default true,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

create index if not exists idx_cartelera_venues_active
  on public.cartelera_venues(venue_name)
  where active = true;

comment on table public.cartelera_venues is
  'Lugares scrapeados de cartelera.cdmx.gob.mx. Esquema 1:1 con out/venues.csv. active=false oculta sin borrar.';

-- ===========================================================================
-- 2. TABLA public.cartelera_events
-- ===========================================================================
--
-- Eventos extraídos de cartelera.cdmx.gob.mx (alcaldía Cuauhtémoc).
-- Esquema idéntico a los headers de out/events.csv.

create table if not exists public.cartelera_events (
  event_id             text primary key,
  event_type           text,
  event_name           text not null,
  event_venue          text,
  -- Formato "dd/mm/yyyy" tal cual lo entrega la API.
  event_date_located   text,
  event_lat            numeric(9, 6),
  event_lon            numeric(9, 6),
  event_thumb          text,
  active               boolean     not null default true,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);

-- event_venue llega como nombre de lugar (no FK). Útil para agrupar.
create index if not exists idx_cartelera_events_venue
  on public.cartelera_events(event_venue)
  where active = true;

create index if not exists idx_cartelera_events_type
  on public.cartelera_events(event_type)
  where active = true;

comment on table public.cartelera_events is
  'Eventos scrapeados de cartelera.cdmx.gob.mx. Esquema 1:1 con out/events.csv. event_date_located en "dd/mm/yyyy" (texto). active=false oculta sin borrar.';

-- ===========================================================================
-- 3. Trigger updated_at
-- ===========================================================================

create or replace function public._cartelera_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists cartelera_venues_touch_updated_at on public.cartelera_venues;
create trigger cartelera_venues_touch_updated_at
  before update on public.cartelera_venues
  for each row execute function public._cartelera_touch_updated_at();

drop trigger if exists cartelera_events_touch_updated_at on public.cartelera_events;
create trigger cartelera_events_touch_updated_at
  before update on public.cartelera_events
  for each row execute function public._cartelera_touch_updated_at();

-- ===========================================================================
-- 4. RLS — default deny
-- ===========================================================================

alter table public.cartelera_venues enable row level security;
alter table public.cartelera_events enable row level security;

commit;
