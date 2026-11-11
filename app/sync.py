"""Sincronização UpSeller -> SQLite (completa, incremental e por SKUs)."""
from __future__ import annotations

import logging
import time
from typing import Callable

from .repo import Repo
from .upseller_client import UpSellerClient, UpSellerError

log = logging.getLogger(__name__)

PAGE_SIZE = 100
OVERLAP_SECONDS = 600  # margem de segurança no marcador incremental
STALE_LOCK_SECONDS = 3600


class SyncBusy(Exception):
    pass


def _acquire(repo: Repo) -> None:
    running = repo.get_state("sync_running")
    if running and time.time() - float(running) < STALE_LOCK_SECONDS:
        raise SyncBusy("já existe uma sincronização em andamento")
    repo.set_state("sync_running", time.time())


def _release(repo: Repo) -> None:
    repo.set_state("sync_running", "")


def sync_warehouses(client: UpSellerClient, repo: Repo) -> list[str]:
    data = client.get_warehouses("ALL").get("data") or []
    repo.upsert_warehouses(data)
    return [str(w["warehouseId"]) for w in data]


def _run(client: UpSellerClient, repo: Repo, kind: str, skus: list[str] | None = None, since: int | None = None,
         progress: Callable[[int, int | None], None] | None = None) -> dict:
    _acquire(repo)
    log_id = repo.log_start(kind)
    started = int(time.time())
    rows = requests = 0
    try:
        wids = sync_warehouses(client, repo)
        requests += 1
        sku_batches = [skus[i:i + 100] for i in range(0, len(skus), 100)] if skus else [None]
        for batch in sku_batches:
            cursor = None
            while True:
                resp = client.page_warehouse_sku(wids, skus=batch, page_no=cursor, page_size=PAGE_SIZE, update_time=since)
                requests += 1
                d = resp.get("data") or {}
                rows += repo.upsert_stock(d.get("skuList") or [], now=started)
                if progress:
                    progress(rows, d.get("totalCount"))
                cursor = d.get("nextPageNo")
                if not d.get("hasMore") or not cursor:
                    break
        removed = 0
        if kind == "full":
            removed = repo.delete_stale(started)
            repo.set_state("last_full_sync", started)
        if kind in ("full", "incremental"):
            repo.set_state("last_incremental_sync", started)
        repo.log_finish(log_id, "ok", rows, requests)
        return {"kind": kind, "rows": rows, "requests": requests, "removed": removed, "seconds": int(time.time()) - started}
    except UpSellerError as e:
        repo.log_finish(log_id, "error", rows, requests, str(e), e.request_id)
        raise
    except Exception as e:  # noqa: BLE001
        repo.log_finish(log_id, "error", rows, requests, f"{type(e).__name__}: {e}")
        raise
    finally:
        _release(repo)


def full_sync(client, repo, progress=None) -> dict:
    return _run(client, repo, "full", progress=progress)


def incremental_sync(client, repo, progress=None) -> dict:
    last = repo.get_state("last_incremental_sync")
    if not last or not repo.get_state("last_full_sync"):
        raise RuntimeError("Nenhuma carga completa feita ainda. Rode a sincronização completa primeiro.")
    return _run(client, repo, "incremental", since=int(float(last)) - OVERLAP_SECONDS, progress=progress)


def sync_skus(client, repo, skus: list[str]) -> dict:
    return _run(client, repo, "skus", skus=skus)


def smart_sync(client, repo, progress=None) -> dict:
    """Completa se nunca houve ou se a última completa foi em outro dia; senão incremental."""
    last_full = repo.get_state("last_full_sync")
    if not last_full or time.strftime("%Y-%m-%d", time.localtime(float(last_full))) != time.strftime("%Y-%m-%d"):
        return full_sync(client, repo, progress)
    return incremental_sync(client, repo, progress)
