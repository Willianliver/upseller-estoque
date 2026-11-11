"""Repositório SQLite: cache de armazéns e estoque. Núcleo compartilhado por web, CLI e MCP."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS warehouses (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT, is_default INTEGER DEFAULT 0, synced_at INTEGER
);
CREATE TABLE IF NOT EXISTS stock (
    warehouse_id TEXT NOT NULL, sku_id TEXT NOT NULL, sku TEXT NOT NULL, title TEXT, sku_type TEXT,
    category TEXT, unit_cost REAL, on_hand REAL, allocated REAL, available REAL, in_transit REAL,
    source_updated INTEGER, synced_at INTEGER NOT NULL,
    PRIMARY KEY (warehouse_id, sku_id)
);
CREATE INDEX IF NOT EXISTS ix_stock_sku ON stock (sku COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS ix_stock_title ON stock (title COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, started_at INTEGER, finished_at INTEGER,
    status TEXT, rows INTEGER, requests INTEGER, error TEXT, request_id TEXT
);
"""

COLUMNS = ("sku_id", "sku", "title", "category", "sku_type", "unit_cost", "on_hand", "allocated", "available", "warehouse_name", "synced_at")


def to_seconds(v: Any) -> int | None:
    """A API mistura segundos e milissegundos (e null)."""
    if v in (None, ""):
        return None
    v = int(v)
    return v // 1000 if v > 10**11 else v


class Repo:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # ---- escrita ----
    def upsert_warehouses(self, items: Iterable[dict]) -> int:
        now, n = int(time.time()), 0
        with self.conn() as c:
            for w in items:
                c.execute(
                    "INSERT INTO warehouses(id,name,type,is_default,synced_at) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET name=excluded.name,type=excluded.type,is_default=excluded.is_default,synced_at=excluded.synced_at",
                    (str(w["warehouseId"]), w.get("warehouseName") or "", w.get("warehouseType"), int(bool(w.get("isDefault"))), now),
                )
                n += 1
        return n

    def upsert_stock(self, items: Iterable[dict], now: int | None = None) -> int:
        now = now or int(time.time())
        rows = []
        for i in items:
            up = i.get("up_info") or {}
            rows.append((
                str(i["warehouseId"]), str(i["skuId"]), i["sku"], i.get("skuTitle"), i.get("skuType"), i.get("categoryName"),
                i.get("unitCost"), up.get("onHand"), up.get("allocated"), up.get("available"), up.get("inTransit"),
                to_seconds(i.get("updateTime")), now,
            ))
        with self.conn() as c:
            c.executemany(
                "INSERT INTO stock(warehouse_id,sku_id,sku,title,sku_type,category,unit_cost,on_hand,allocated,available,in_transit,source_updated,synced_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(warehouse_id,sku_id) DO UPDATE SET "
                "sku=excluded.sku,title=excluded.title,sku_type=excluded.sku_type,category=excluded.category,unit_cost=excluded.unit_cost,"
                "on_hand=excluded.on_hand,allocated=excluded.allocated,available=excluded.available,in_transit=excluded.in_transit,"
                "source_updated=excluded.source_updated,synced_at=excluded.synced_at",
                rows,
            )
        return len(rows)

    def delete_stale(self, before: int) -> int:
        """Remove SKUs não vistos numa carga completa iniciada em `before`."""
        with self.conn() as c:
            return c.execute("DELETE FROM stock WHERE synced_at < ?", (before,)).rowcount

    def set_state(self, key: str, value: Any) -> None:
        with self.conn() as c:
            c.execute("INSERT INTO sync_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

    def get_state(self, key: str, default: str | None = None) -> str | None:
        with self.conn() as c:
            r = c.execute("SELECT value FROM sync_state WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    # ---- agendamento (persistente: sobrevive a reinicializações) ----
    def scheduler_enabled(self) -> bool:
        return self.get_state("scheduler_enabled", "1") != "0"

    def set_scheduler_enabled(self, enabled: bool) -> None:
        self.set_state("scheduler_enabled", "1" if enabled else "0")

    def log_start(self, kind: str) -> int:
        with self.conn() as c:
            return c.execute("INSERT INTO sync_log(kind,started_at,status) VALUES(?,?,'running')", (kind, int(time.time()))).lastrowid

    def log_finish(self, log_id: int, status: str, rows: int, requests: int, error: str | None = None, request_id: str | None = None) -> None:
        with self.conn() as c:
            c.execute(
                "UPDATE sync_log SET finished_at=?,status=?,rows=?,requests=?,error=?,request_id=? WHERE id=?",
                (int(time.time()), status, rows, requests, error, request_id, log_id),
            )

    # ---- leitura ----
    def list_warehouses(self) -> list[dict]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT id,name,type,is_default FROM warehouses ORDER BY is_default DESC,name")]

    _SELECT = (
        "SELECT s.sku_id,s.sku,s.title,s.category,s.sku_type,s.unit_cost,s.on_hand,s.allocated,s.available,"
        "w.name AS warehouse_name,s.synced_at FROM stock s LEFT JOIN warehouses w ON w.id=s.warehouse_id"
    )
    ORDERABLE = {"sku": "s.sku", "title": "s.title", "category": "s.category", "on_hand": "s.on_hand", "available": "s.available", "unit_cost": "s.unit_cost"}

    def get_by_skus(self, skus: list[str], warehouse_id: str | None = None) -> list[dict]:
        if not skus:
            return []
        out: list[dict] = []
        with self.conn() as c:
            for chunk in (skus[i:i + 500] for i in range(0, len(skus), 500)):
                q = f"{self._SELECT} WHERE s.sku COLLATE NOCASE IN ({','.join('?' * len(chunk))})"
                args: list[Any] = list(chunk)
                if warehouse_id:
                    q += " AND s.warehouse_id=?"
                    args.append(warehouse_id)
                out += [dict(r) for r in c.execute(q, args)]
        return out

    def search(self, term: str = "", warehouse_id: str | None = None, order: str = "sku", desc: bool = False,
               limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        where, args = [], []
        if term:
            like = f"%{term.replace('%', '').replace('_', '')}%"
            where.append("(s.sku LIKE ? OR s.title LIKE ?)")
            args += [like, like]
        if warehouse_id:
            where.append("s.warehouse_id=?")
            args.append(warehouse_id)
        w = (" WHERE " + " AND ".join(where)) if where else ""
        col = self.ORDERABLE.get(order, "s.sku")
        with self.conn() as c:
            total = c.execute(f"SELECT COUNT(*) FROM stock s{w}", args).fetchone()[0]
            rows = c.execute(f"{self._SELECT}{w} ORDER BY {col} {'DESC' if desc else 'ASC'} LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
        return [dict(r) for r in rows], total

    def status(self) -> dict:
        with self.conn() as c:
            n = c.execute("SELECT COUNT(*) FROM stock").fetchone()[0]
            oldest, newest = c.execute("SELECT MIN(synced_at),MAX(synced_at) FROM stock").fetchone()
            last = c.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
            ok = c.execute("SELECT * FROM sync_log WHERE status='ok' ORDER BY id DESC LIMIT 1").fetchone()
        return {
            "skus": n, "oldest_synced": oldest, "newest_synced": newest,
            "last_run": dict(last) if last else None, "last_ok": dict(ok) if ok else None,
            "last_full": self.get_state("last_full_sync"), "last_incremental": self.get_state("last_incremental_sync"),
        }
