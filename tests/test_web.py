import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import web
from app.repo import Repo
from app.service import parse_skus

SKU = json.loads((Path(__file__).parent / "fixtures" / "warehouse_sku.json").read_text(encoding="utf-8"))
WH = json.loads((Path(__file__).parent / "fixtures" / "warehouses.json").read_text(encoding="utf-8"))


@pytest.fixture
def client(tmp_path, monkeypatch):
    r = Repo(tmp_path / "w.db")
    r.upsert_warehouses(WH["data"])
    r.upsert_stock(SKU["data"]["skuList"])
    monkeypatch.setattr(web, "repo", r)
    return TestClient(web.app)


def test_parse_skus_dedup_and_split():
    assert parse_skus("A\n a \r\nB;C\n\n") == ["A", "B", "C"]


def test_home_ok(client):
    assert client.get("/").status_code == 200


def test_list_search_shows_found_and_missing(client):
    h = client.get("/", params={"skus": "REF-200\nNAO-EXISTE"}).text
    assert "REF-200" in h and "NAO-EXISTE" in h and "não encontrado" in h


def test_text_search(client):
    assert "PALMILHA 121" in client.get("/", params={"q": "palmilha"}).text


def test_export_xlsx(client):
    r = client.get("/export.xlsx", params={"q": "REF"})
    ws = load_workbook(io.BytesIO(r.content)).active
    assert ws["B1"].value == "SKU" and ws.max_row == 3


def test_html_escaped(client):
    assert "<script>" not in client.get("/", params={"q": "<script>"}).text


def test_no_token_in_page(client):
    assert "UPSELLER_API_TOKEN" not in client.get("/").text


def test_scheduler_toggle_persists(client, tmp_path):
    assert web.repo.scheduler_enabled() is True          # padrão: ativado
    assert "Ativada" in client.get("/config").text
    client.post("/config/scheduler", data={"enabled": 0}, follow_redirects=False)
    assert web.repo.scheduler_enabled() is False
    assert "Desativada" in client.get("/config").text
    # "reinício": novo objeto Repo sobre o mesmo arquivo continua desativado
    assert Repo(tmp_path / "w.db").scheduler_enabled() is False
    client.post("/config/scheduler", data={"enabled": 1}, follow_redirects=False)
    assert Repo(tmp_path / "w.db").scheduler_enabled() is True


def test_config_page_shows_scheduler_not_detected_without_heartbeat(client):
    assert "não detectado" in client.get("/config").text
