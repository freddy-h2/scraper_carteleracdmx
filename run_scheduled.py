"""Loop que ejecuta ingest_supabase.main() una vez al día a SCHEDULE_HOUR.

Hora se interpreta en la TZ del container (Dockerfile: America/Mexico_City).
Sin cron nativo en EasyPanel → `time.sleep` hasta el próximo horario.

Env:
  SCHEDULE_HOUR=4     hora local (0-23). Default: 4am CDMX.
  SCHEDULE_MINUTE=0   minuto local.
  RUN_ON_START=0      si 1, corre inmediatamente al arrancar (útil para probar).
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta

from ingest_supabase import main as run_ingest


def _seconds_until(hour: int, minute: int) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main_loop() -> int:
    hour = int(os.environ.get("SCHEDULE_HOUR", "4"))
    minute = int(os.environ.get("SCHEDULE_MINUTE", "0"))
    run_on_start = os.environ.get("RUN_ON_START", "0") == "1"

    print(
        f"[runner] schedule {hour:02d}:{minute:02d} local "
        f"run_on_start={run_on_start}",
        file=sys.stderr,
        flush=True,
    )

    if run_on_start:
        try:
            run_ingest()
        except Exception as e:
            print(f"[runner] error en run-on-start: {e}", file=sys.stderr, flush=True)

    while True:
        secs = _seconds_until(hour, minute)
        next_run = (datetime.now() + timedelta(seconds=secs)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        print(
            f"[runner] durmiendo {secs / 3600:.2f}h hasta {next_run}",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(secs)
        try:
            run_ingest()
        except Exception as e:
            print(f"[runner] ingest falló: {e}", file=sys.stderr, flush=True)
        # Evita doble-disparo si ingest termina antes del próximo minuto.
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main_loop() or 0)
