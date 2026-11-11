"""Funções de negócio compartilhadas por web, CLI e MCP (sem duplicar lógica)."""
from __future__ import annotations

import io
import time
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

from .repo import Repo

HEADERS = ["Código do Produto", "SKU", "Nome do Produto", "Categorias", "Custo de Compra", "Armazém",
           "Estoque físico", "Reservado", "Disponível", "Atualizado em"]


def parse_skus(text: str) -> list[str]:
    seen, out = set(), []
    for line in (text or "").replace(";", "\n").replace("\r", "\n").split("\n"):
        s = line.strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def age_text(ts: float | int | None) -> str:
    if not ts:
        return "nunca"
    d = int(time.time() - float(ts))
    if d < 60:
        return "agora"
    if d < 3600:
        return f"{d // 60} min"
    if d < 86400:
        return f"{d // 3600} h {(d % 3600) // 60} min"
    return f"{d // 86400} d"


def consultar(repo: Repo, skus: list[str] | None = None, term: str = "", warehouse_id: str | None = None,
              order: str = "sku", desc: bool = False, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    if skus:
        rows = repo.get_by_skus(skus, warehouse_id)
        found = {r["sku"].lower() for r in rows}
        missing = [s for s in skus if s.lower() not in found]
        key = {"sku": "sku", "title": "title"}.get(order, order)
        rows.sort(key=lambda r: (r.get(key) is None, r.get(key) if not isinstance(r.get(key), str) else r[key].lower()), reverse=desc)
        total = len(rows)
        rows = rows[offset:offset + limit]
    else:
        rows, total = repo.search(term, warehouse_id, order, desc, limit, offset)
        missing = []
    return {"rows": rows, "total": total, "missing": missing, "truncated": total > offset + len(rows)}


def export_xlsx(rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Estoque"
    ws.append(HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([r["sku_id"], r["sku"], r["title"], r["category"], r["unit_cost"], r["warehouse_name"],
                   r["on_hand"], r["allocated"], r["available"],
                   time.strftime("%d/%m/%Y %H:%M", time.localtime(r["synced_at"])) if r["synced_at"] else None])
    ws.freeze_panes = "A2"
    for col, w in zip("ABCDEFGHIJ", (22, 34, 50, 22, 16, 18, 14, 12, 12, 18)):
        ws.column_dimensions[col].width = w
    ws["A1"].number_format = "@"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
