"""Servidor MCP (stdio). Uso: python -m app.mcp_server
Atenção: em stdio, NUNCA escrever em stdout (quebra o protocolo). Logs vão para stderr."""
from __future__ import annotations

import logging
import sys
import threading

from mcp.server.fastmcp import FastMCP

from .config import Settings
from .repo import Repo
from .service import age_text, consultar, parse_skus
from .sync import SyncBusy, smart_sync, sync_skus
from .upseller_client import UpSellerClient, UpSellerError

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

mcp = FastMCP("upseller-estoque")
_settings = Settings()
_repo = Repo(_settings.db_path)
MAX_ROWS = 100


def _n(v) -> str:
    if v is None:
        return "-"
    return str(int(v)) if float(v).is_integer() else str(v)


def _warehouse_id(name: str | None) -> str | None:
    if not name:
        return None
    for w in _repo.list_warehouses():
        if name.lower() in w["name"].lower() or name == w["id"]:
            return w["id"]
    raise ValueError(f"armazém não encontrado: {name}")


def _table(rows: list[dict], detalhes: bool) -> list[str]:
    head = ["sku", "disp", "fisico", "reserv", "idade"] + (["nome", "cat", "custo", "armazem"] if detalhes else [])
    out = ["\t".join(head)]
    for r in rows:
        cols = [r["sku"], _n(r["available"]), _n(r["on_hand"]), _n(r["allocated"]), age_text(r["synced_at"])]
        if detalhes:
            cols += [r["title"] or "-", r["category"] or "-", _n(r["unit_cost"]), r["warehouse_name"] or "-"]
        out.append("\t".join(cols))
    return out


@mcp.tool()
def consultar_estoque(skus: list[str], armazem: str | None = None, detalhes: bool = False) -> str:
    """Estoque dos SKUs informados (cache local). disp=disponível, fisico=em mãos, reserv=reservado. detalhes=true inclui nome/categoria/custo."""
    skus = parse_skus("\n".join(skus))
    if not skus:
        return "erro: informe ao menos 1 SKU"
    try:
        res = consultar(_repo, skus, warehouse_id=_warehouse_id(armazem), limit=MAX_ROWS)
    except ValueError as e:
        return f"erro: {e}"
    head = f"total: {res['total']} | truncado: {str(res['truncated']).lower()}"
    if res["missing"]:
        head += " | nao_encontrados: " + ",".join(res["missing"][:30])
    return "\n".join([head, *_table(res["rows"], detalhes)])


@mcp.tool()
def buscar_sku(termo: str, limite: int = 20, armazem: str | None = None) -> str:
    """Busca parcial por SKU ou nome no cache."""
    try:
        res = consultar(_repo, term=termo.strip(), warehouse_id=_warehouse_id(armazem), limit=max(1, min(limite, MAX_ROWS)))
    except ValueError as e:
        return f"erro: {e}"
    head = f"total: {res['total']} | truncado: {str(res['truncated']).lower()}"
    lines = ["\t".join(["sku", "nome", "disp"])]
    lines += [f"{r['sku']}\t{(r['title'] or '-')[:60]}\t{_n(r['available'])}" for r in res["rows"]]
    return "\n".join([head, *lines])


@mcp.tool()
def listar_armazens() -> str:
    """Lista os armazéns."""
    ws = _repo.list_warehouses()
    return "\n".join(["id\tnome\ttipo", *(f"{w['id']}\t{w['name']}\t{w['type']}" for w in ws)]) if ws else "nenhum armazém no cache"


@mcp.tool()
def status_sincronizacao() -> str:
    """Estado do cache: quantidade de SKUs, idade do dado e última sincronização."""
    s = _repo.status()
    lr = s["last_run"]
    parts = [f"skus: {s['skus']}", f"dado_mais_antigo: {age_text(s['oldest_synced'])}", f"dado_mais_novo: {age_text(s['newest_synced'])}",
             f"em_andamento: {str(bool(_repo.get_state('sync_running'))).lower()}"]
    if lr:
        parts.append(f"ultima: {lr['kind']}/{lr['status']}/{lr['rows']} linhas")
        if lr["error"]:
            parts.append(f"erro: {lr['error']}")
    return " | ".join(parts)


def _bg_full() -> None:
    try:
        client = UpSellerClient(_settings)
        try:
            smart_sync(client, _repo)
        finally:
            client.close()
    except Exception as e:  # noqa: BLE001
        logging.error("sync em segundo plano falhou: %s", e)


@mcp.tool()
def atualizar_cache(skus: list[str] | None = None) -> str:
    """Atualiza o cache. Com skus: busca esses SKUs no UpSeller agora (até 300). Sem skus: sincronização geral em segundo plano (leva minutos; acompanhe com status_sincronizacao)."""
    if _repo.get_state("sync_running"):
        return "ja_em_andamento"
    lst = parse_skus("\n".join(skus or []))
    if not lst:
        threading.Thread(target=_bg_full, daemon=True).start()
        return "iniciado em segundo plano"
    client = UpSellerClient(_settings)
    try:
        r = sync_skus(client, _repo, lst[:300])
        return f"ok: {r['rows']} SKUs atualizados" + (f" (limitado a 300 de {len(lst)})" if len(lst) > 300 else "")
    except (UpSellerError, SyncBusy) as e:
        return f"erro: {e}"
    finally:
        client.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
