-- 0011: eventos y lugares de la alcaldía
--
-- WHY: el agente necesita responder preguntas tipo "¿qué eventos hay este
-- fin de semana?" o "¿dónde queda la casa de la cultura?". Hasta ahora esa
-- información vive en PDFs dentro de public.knowledge, lo que obliga al
-- agente a hacer búsqueda semántica sobre texto libre y a recalcular fechas
-- a mano. Con tablas estructuradas (events, places) el tool correspondiente
-- puede filtrar por rango de fechas, categoría o cercanía sin LLM overhead.
--
-- RELACIÓN events → places: un evento opcionalmente referencia un lugar
-- registrado. Si el evento ocurre en un sitio no catalogado o es virtual,
-- se deja place_id null y se usa location_text como descripción libre.
--
-- CONVENCIÓN department: misma lista lowercase snake_case que admin_users
-- ('cultura','deportes','turismo','salud','seguridad','programas_sociales',
-- 'tramites','medio_ambiente','comunicacion'). Null = transversal. No se
-- fuerza enum porque la lista va a crecer.
--
-- INGESTA EXTERNA: los campos source+source_id permiten upsert idempotente
-- desde scrapers (cartelera.cdmx.gob.mx, etc.). source='cartelera_cdmx' +
-- source_id=<event_id|venue_id> identifican unívocamente el origen. Null en
-- ambos = registro capturado manualmente desde el admin.
--
-- RLS: mismo patrón que public.knowledge (migration 0008). RLS on, cero
-- políticas. El agente Python y las rutas Next.js consultan con
-- service_role (BYPASSRLS), y el cliente del navegador nunca toca estas
-- tablas directamente — si se filtrara la anon key, Postgres rechaza en
-- vez de leakear rows.
--
-- Cómo aplicar:
--   psql "$DATABASE_URL" -f agent/migrations/0011_events_and_places.sql
-- o:
--   supabase db push
--
-- Idempotente: seguro re-ejecutar.

begin;

-- ===========================================================================
-- 1. TABLA public.places
-- ===========================================================================
--
-- Lugares administrados o recomendados por la alcaldía: parques, bibliotecas,
-- casas de la cultura, centros de salud, oficinas de trámite, museos, etc.
-- Consultada por el agente para responder "¿dónde queda X?" y como FK de
-- public.events.

create table if not exists public.places (
  id            uuid primary key default gen_random_uuid(),
  -- Identificadores de origen. Null/null = creado a mano. Con valor =
  -- importado desde un scraper (p.ej. 'cartelera_cdmx' + venue_id numérico).
  source        text,
  source_id     text,
  name          text not null,
  description   text,
  -- 'parque','biblioteca','casa_cultura','centro_salud','oficina','museo',
  -- 'deportivo','mercado','punto_violeta', etc. Slugs libres lowercase.
  category      text,
  -- Mismo vocabulario que admin_users.department (null = transversal).
  department    text,
  address       text,
  neighborhood  text,
  -- Coordenadas WGS84. Null si no se conoce. Pareja (lat,lng) siempre
  -- viaja junta — si una es null, la otra también debería serlo.
  latitude      numeric(9, 6),
  longitude     numeric(9, 6),
  -- Horario en texto libre ("L-V 9-18, S 9-14"). JSON estructurado se
  -- puede meter en metadata si hace falta un parser.
  hours         text,
  phone         text,
  email         text,
  website       text,
  image_url     text,
  tags          text[] not null default '{}'::text[],
  metadata      jsonb  not null default '{}'::jsonb,
  -- Soft-publish. active=false lo oculta del agente sin borrar el histórico.
  active        boolean not null default true,
  -- Admin que creó el registro. Null si se migró desde otra fuente.
  created_by    uuid references public.admin_users(id) on delete set null,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint places_coords_paired
    check ((latitude is null) = (longitude is null)),
  constraint places_source_paired
    check ((source is null) = (source_id is null))
);

-- Unicidad parcial: un mismo (source, source_id) nunca aparece dos veces,
-- pero múltiples registros manuales (source=null) sí conviven.
create unique index if not exists uq_places_source
  on public.places(source, source_id)
  where source is not null;

create index if not exists idx_places_active_category
  on public.places(category)
  where active = true;

create index if not exists idx_places_active_department
  on public.places(department)
  where active = true;

create index if not exists idx_places_tags
  on public.places using gin(tags);

comment on table public.places is
  'Lugares de la alcaldía consultados por el agente (parques, bibliotecas, oficinas, etc.). source+source_id identifican registros importados desde scrapers (upsert idempotente). active=false oculta sin borrar. Coordenadas opcionales para búsquedas por cercanía.';

-- ===========================================================================
-- 2. TABLA public.events
-- ===========================================================================
--
-- Eventos oficiales: culturales, deportivos, académicos, convocatorias, etc.
-- place_id referencia places cuando el evento ocurre en un sitio catalogado;
-- si no, location_text guarda la descripción libre o 'virtual'.

create table if not exists public.events (
  id                uuid primary key default gen_random_uuid(),
  source            text,
  source_id         text,
  title             text not null,
  description       text,
  starts_at         timestamptz not null,
  -- Null para eventos puntuales/sin cierre definido.
  ends_at           timestamptz,
  place_id          uuid references public.places(id) on delete set null,
  -- Fallback cuando no hay place_id (evento virtual, en calle, sede externa).
  location_text     text,
  -- 'cultural','deportivo','educativo','convocatoria','salud','tramite',…
  category          text,
  department        text,
  is_free           boolean not null default true,
  -- En la moneda local. Null si is_free o si todavía no está definido.
  price             numeric(10, 2),
  registration_url  text,
  contact_phone     text,
  contact_email     text,
  image_url         text,
  tags              text[] not null default '{}'::text[],
  metadata          jsonb  not null default '{}'::jsonb,
  active            boolean not null default true,
  created_by        uuid references public.admin_users(id) on delete set null,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  constraint events_ends_after_starts
    check (ends_at is null or ends_at >= starts_at),
  constraint events_price_requires_paid
    check (price is null or is_free = false),
  constraint events_has_location
    check (place_id is not null or location_text is not null),
  constraint events_source_paired
    check ((source is null) = (source_id is null))
);

create unique index if not exists uq_events_source
  on public.events(source, source_id)
  where source is not null;

-- Query típica del agente: "eventos activos a partir de ahora, opcionalmente
-- filtrados por categoría/departamento". starts_at asc cubre eso.
create index if not exists idx_events_active_starts_at
  on public.events(starts_at)
  where active = true;

create index if not exists idx_events_active_category
  on public.events(category, starts_at)
  where active = true;

create index if not exists idx_events_active_department
  on public.events(department, starts_at)
  where active = true;

create index if not exists idx_events_place
  on public.events(place_id)
  where place_id is not null;

create index if not exists idx_events_tags
  on public.events using gin(tags);

comment on table public.events is
  'Eventos oficiales de la alcaldía. starts_at/ends_at en timestamptz. place_id opcional (fallback a location_text para eventos virtuales o en sedes no catalogadas). source+source_id para ingesta idempotente desde scrapers. active=false oculta sin borrar.';

-- ===========================================================================
-- 3. Trigger updated_at (reutiliza el patrón de _admin_users_touch_updated_at)
-- ===========================================================================

create or replace function public._places_events_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists places_touch_updated_at on public.places;
create trigger places_touch_updated_at
  before update on public.places
  for each row execute function public._places_events_touch_updated_at();

drop trigger if exists events_touch_updated_at on public.events;
create trigger events_touch_updated_at
  before update on public.events
  for each row execute function public._places_events_touch_updated_at();

-- ===========================================================================
-- 4. RLS — default deny (mismo patrón que knowledge/users/conversations)
-- ===========================================================================
--
-- RLS activado, cero políticas → authenticated y anon no ven nada.
-- service_role bypassa (lo que usa tanto el admin Next.js como el agente
-- Python). Si en el futuro se quiere exponer /events directamente al
-- navegador sin pasar por la API, se pueden añadir políticas aquí.

alter table public.places enable row level security;
alter table public.events enable row level security;

commit;
