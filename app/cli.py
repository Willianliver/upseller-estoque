"""CLI de manutenção. Uso: python -m app.cli <comando>"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from .config import Settings
from .repo import Repo
from .sync import SyncBusy, full_sync, incremental_sync, smart_sync, sync_skus
from .upseller_client import UpSellerClient, UpSellerError


def fmt_ts(ts) -> str:
    return time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(float(ts))) if ts not in (None, "") else "—"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="sincroniza o cache")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--full", action="store_true", help="carga completa")
    g.add_argument("--incremental", action="store_true", help="somente alterados")
    q = sub.add_parser("sync-skus", help="atualiza só os SKUs informados")
    q.add_argument("skus", nargs="+")
    sub.add_parser("status", help="estado do cache")
    c = sub.add_parser("consultar", help="consulta no cache")
    c.add_argument("skus", nargs="+")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    st = Settings()
    repo = Repo(st.db_path)

    if a.cmd == "status":
        s_ = repo.status()
        print(f"SKUs no cache: {s_['skus']}")
        print(f"Dado mais antigo: {fmt_ts(s_['oldest_synced'])} | mais novo: {fmt_ts(s_['newest_synced'])}")
        print(f"Última completa: {fmt_ts(s_['last_full'])} | última incremental: {fmt_ts(s_['last_incremental'])}")
        lr = s_["last_run"]
        if lr:
            print(f"Última execução: {lr['kind']} / {lr['status']} / {lr['rows']} linhas / {lr['requests']} req" + (f" / erro: {lr['error']} (requestId={lr['request_id']})" if lr["error"] else ""))
        return 0

    if a.cmd == "consultar":
        for r in repo.get_by_skus(a.skus):
            print(f"{r['sku']}\t{r['title']}\tdisp={r['available']}\tfísico={r['on_hand']}\treserv={r['allocated']}\t({fmt_ts(r['synced_at'])})")
        return 0

    client = UpSellerClient(st)
    prog = lambda rows, total: print(f"\r  {rows}/{total or '?'}", end="", flush=True)  # noqa: E731
    try:
        if a.cmd == "sync-skus":
            res = sync_skus(client, repo, a.skus)
        elif a.cmd == "sync" and a.full:
            res = full_sync(client, repo, prog)
        elif a.cmd == "sync" and a.incremental:
            res = incremental_sync(client, repo, prog)
        else:
            res = smart_sync(client, repo, prog)
        print("\n", res)
        return 0
    except SyncBusy as e:
        print(f"\n{e}", file=sys.stderr)
        return 2
    except UpSellerError as e:
        print(f"\nErro da API: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
