"""Interface web local (127.0.0.1). Uso: python -m app.web"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .config import Settings
from .repo import Repo
from .service import age_text, consultar, export_xlsx, parse_skus
from .sync import SyncBusy, smart_sync, sync_skus
from .upseller_client import UpSellerClient, UpSellerError

log = logging.getLogger(__name__)
settings = Settings()
repo = Repo(settings.db_path)
app = FastAPI(title="Estoque UpSeller", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["age"] = age_text
PAGE = 50
_last_error: dict = {"msg": None}


def _bg(fn, *args):
    def run():
        try:
            client = UpSellerClient(settings)
            try:
                fn(client, repo, *args)
                _last_error["msg"] = None
            finally:
                client.close()
        except SyncBusy as e:
            _last_error["msg"] = str(e)
        except UpSellerError as e:
            _last_error["msg"] = f"Erro da API: {e}"  # sem credenciais; inclui requestId
        except Exception as e:  # noqa: BLE001
            log.exception("falha na sincronização")
            _last_error["msg"] = f"Falha: {type(e).__name__}"
    threading.Thread(target=run, daemon=True).start()


def _running() -> bool:
    v = repo.get_state("sync_running")
    return bool(v)


@app.get("/")
def index(request: Request, q: str = "", skus: str = "", wh: str = "", order: str = "sku", desc: int = 0, page: int = 1):
    lst = parse_skus(skus)
    page = max(page, 1)
    res = consultar(repo, lst or None, q.strip(), wh or None, order, bool(desc), PAGE, (page - 1) * PAGE)
    return templates.TemplateResponse(request, "index.html", {
        "res": res, "q": q, "skus": skus, "wh": wh, "order": order, "desc": desc, "page": page, "page_size": PAGE,
        "warehouses": repo.list_warehouses(), "status": repo.status(), "running": _running(), "error": _last_error["msg"],
        "searched": bool(lst or q.strip() or wh),
    })


@app.get("/config")
def config_page(request: Request):
    hb = repo.get_state("scheduler_heartbeat")
    alive = bool(hb) and (time.time() - float(hb)) < 120  # o agendador bate a cada 30 s
    return templates.TemplateResponse(request, "config.html", {
        "enabled": repo.scheduler_enabled(), "alive": alive, "heartbeat": float(hb) if hb else None,
        "last_start": repo.get_state("scheduler_last_start"), "status": repo.status(),
        "interval": os.getenv("SYNC_INTERVAL_MINUTES", "60"),
        "window": f"{os.getenv('SYNC_WINDOW_START', '08:30')}–{os.getenv('SYNC_WINDOW_END', '16:30')}",
        "days": os.getenv("SYNC_WEEKDAYS", "mon,tue,wed,thu,fri"),
    })


@app.post("/config/scheduler")
def toggle_scheduler(enabled: int = Form(...)):
    repo.set_scheduler_enabled(bool(enabled))
    log.info("agendamento %s pelo usuário", "ativado" if enabled else "desativado")
    return RedirectResponse("/config", status_code=303)


@app.post("/sync")
def sync_now():
    if not _running():
        _bg(smart_sync)
    return RedirectResponse("/", status_code=303)


@app.post("/live")
def live(skus: str = Form("")):
    lst = parse_skus(skus)[:300]
    if lst and not _running():
        _bg(sync_skus, lst)
    return RedirectResponse("/", status_code=303)


@app.get("/export.xlsx")
def export(q: str = "", skus: str = "", wh: str = "", order: str = "sku", desc: int = 0):
    lst = parse_skus(skus)
    res = consultar(repo, lst or None, q.strip(), wh or None, order, bool(desc), 100_000, 0)
    return Response(export_xlsx(res["rows"]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="estoque.xlsx"'})


if __name__ == "__main__":
    import sys

    import uvicorn

    from .config import ROOT
    if sys.stderr is None or sys.stdout is None:  # pythonw (sem console): o uvicorn exige stderr
        (ROOT / "logs").mkdir(exist_ok=True)
        _f = open(ROOT / "logs" / "web.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or _f
        sys.stderr = sys.stderr or _f
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("WEB_PORT", "8000")))  # host fixo: somente local
