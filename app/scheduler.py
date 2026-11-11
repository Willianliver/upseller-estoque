"""Agendador independente de IA. Uso: python -m app.scheduler
Sincroniza a cada SYNC_INTERVAL_MINUTES, só dentro da janela (dias úteis, SYNC_WINDOW_START–END)."""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, time as dtime
from logging.handlers import RotatingFileHandler

from .config import ROOT, Settings
from .repo import Repo
from .sync import SyncBusy, smart_sync
from .upseller_client import UpSellerClient, UpSellerError

log = logging.getLogger("scheduler")
_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _t(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def in_window(now: datetime, start: str, end: str, weekdays: list[str]) -> bool:
    return _DAYS[now.weekday()] in weekdays and _t(start) <= now.time() <= _t(end)


def is_due(now_ts: float, last_start_ts: float | None, interval_min: int) -> bool:
    return last_start_ts is None or now_ts - last_start_ts >= interval_min * 60


def run_once(settings: Settings, repo: Repo) -> None:
    client = UpSellerClient(settings)
    try:
        log.info("sincronização iniciada")
        log.info("resultado: %s", smart_sync(client, repo))
    except SyncBusy as e:
        log.info("%s", e)
    except UpSellerError as e:
        log.error("erro da API: %s", e)  # inclui code e requestId; nunca credenciais
    except Exception:  # noqa: BLE001
        log.exception("falha inesperada na sincronização")
    finally:
        client.close()


def main() -> None:
    (ROOT / "logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = RotatingFileHandler(ROOT / "logs" / "scheduler.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    sh = logging.StreamHandler()
    for h in (fh, sh):
        h.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[fh, sh])

    settings = Settings()
    settings.validate()
    repo = Repo(settings.db_path)
    interval = int(os.getenv("SYNC_INTERVAL_MINUTES", "60"))
    start, end = os.getenv("SYNC_WINDOW_START", "08:30"), os.getenv("SYNC_WINDOW_END", "16:30")
    days = [d.strip().lower() for d in os.getenv("SYNC_WEEKDAYS", "mon,tue,wed,thu,fri").split(",")]
    log.info("agendador ativo: a cada %d min, %s–%s, dias %s", interval, start, end, ",".join(days))

    while True:
        try:
            now = datetime.now()
            repo.set_state("scheduler_heartbeat", now.timestamp())  # sinal de vida para a tela de configurações
            last = repo.get_state("scheduler_last_start")
            # Interruptor lido a cada ciclo: desativado = nunca sincroniza, mesmo após reiniciar o computador
            if repo.scheduler_enabled() and in_window(now, start, end, days) and is_due(now.timestamp(), float(last) if last else None, interval):
                repo.set_state("scheduler_last_start", now.timestamp())
                run_once(settings, repo)
        except Exception:  # noqa: BLE001
            log.exception("erro no laço do agendador")
        time.sleep(30)


if __name__ == "__main__":
    main()
