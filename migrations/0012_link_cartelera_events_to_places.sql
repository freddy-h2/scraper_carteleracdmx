-- 0012: enlaza public.events.place_id con public.places para registros
-- importados desde cartelera_cdmx.
--
-- WHY: la importación por CSV carga places y events por separado. Como
-- place_id es un UUID asignado por Postgres, no se puede resolver al
-- momento de generar el CSV. En places.metadata->'event_ids' guardamos la
-- lista de event_ids que pertenecen a cada venue (campo venue_event_list
-- de la API). Esta migration corre una vez después de importar ambos CSVs
-- para rellenar events.place_id.
--
-- Idempotente: solo toca filas con place_id null donde hay match.

begin;

update public.events e
set place_id = p.id
from public.places p
cross join lateral jsonb_array_elements_text(p.metadata->'event_ids') as ev(event_id)
where e.source = 'cartelera_cdmx'
  and p.source = 'cartelera_cdmx'
  and e.place_id is null
  and ev.event_id = e.source_id;

commit;
