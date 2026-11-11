import json
import time
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.repo import Repo, to_seconds
from app.sync import SyncBusy, full_sync, incremental_sync, smart_sync, sync_skus
from app.upseller_client import RateLimiter, UpSellerClient, UpSellerError

FIX = Path(__file__).parent / "fixtures"
WH = json.loads((FIX / "warehouses.json").read_text(encoding="utf-8"))
SKU = json.loads((FIX / "warehouse_sku.json").read_text(encoding="utf-8"))


def make_client(handler):
    st = Settings(client_id="id", api_token="tok", rate_limit_per_minute=10_000)
    return UpSellerClient(st, transport=httpx.MockTransport(handler))


def api_handler(calls):
    def h(req: httpx.Request):
        body = json.loads(req.content)
        calls.append((req.url.path, body))
        if req.url.path.endswith("getWarehouseList/v1"):
            return httpx.Response(200, json=WH)
        # 2 páginas: cursor "p2" na primeira
        items = SKU["data"]["skuList"]
        if body.get("pageNo") == "p2":
            data = {"skuList": items[2:], "nextPageNo": None, "hasMore": False, "totalCount": 3}
        else:
            data = {"skuList": items[:2], "nextPageNo": "p2", "hasMore": True, "totalCount": 3}
        return httpx.Response(200, json={"code": 0, "data": data})
    return h


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path / "t.db")


def test_to_seconds():
    assert to_seconds(1793284033) == 1793284033
    assert to_seconds(1792758287545) == 1792758287
    assert to_seconds(None) is None


def test_full_sync_paginates_and_stores(repo):
    calls = []
    res = full_sync(make_client(api_handler(calls)), repo)
    assert res["rows"] == 3 and res["requests"] == 3
    assert repo.status()["skus"] == 3
    assert calls[1][1].get("pageNo") is None and calls[2][1]["pageNo"] == "p2"
    r = repo.get_by_skus(["ref-200"])[0]  # case-insensitive
    assert r["available"] == 5000 and r["warehouse_name"] == "My Warehouse"


def test_kit_null_fields_ok(repo):
    full_sync(make_client(api_handler([])), repo)
    kit = [r for r in repo.get_by_skus([i["sku"] for i in SKU["data"]["skuList"]]) if r["sku_type"] == "KIT"][0]
    assert kit["allocated"] is None and kit["category"] == "Camisetas"


def test_incremental_requires_full(repo):
    with pytest.raises(RuntimeError):
        incremental_sync(make_client(api_handler([])), repo)


def test_incremental_sends_update_time_seconds(repo):
    calls = []
    c = make_client(api_handler(calls))
    full_sync(c, repo)
    calls.clear()
    incremental_sync(c, repo)
    sent = calls[1][1]["updateTime"]
    assert 10**9 < sent < 10**11  # segundos


def test_full_removes_stale(repo):
    c = make_client(api_handler([]))
    full_sync(c, repo)
    with repo.conn() as db:
        db.execute("INSERT INTO stock(warehouse_id,sku_id,sku,synced_at) VALUES('x','9','VELHO',1)")
    time.sleep(1)
    res = full_sync(c, repo)
    assert res["removed"] == 1 and not repo.get_by_skus(["VELHO"])


def test_sync_skus_sends_skulist(repo):
    calls = []
    sync_skus(make_client(api_handler(calls)), repo, ["REF-121"])
    assert calls[1][1]["skuList"] == ["REF-121"]


def test_smart_sync_full_then_incremental(repo):
    c = make_client(api_handler([]))
    assert smart_sync(c, repo)["kind"] == "full"
    assert smart_sync(c, repo)["kind"] == "incremental"


def test_lock_blocks_concurrent(repo):
    repo.set_state("sync_running", time.time())
    with pytest.raises(SyncBusy):
        full_sync(make_client(api_handler([])), repo)


def test_error_logged_with_request_id(repo):
    def h(req):
        return httpx.Response(200, json={"code": 4001, "message": "ruim", "requestId": "abc123"})
    with pytest.raises(UpSellerError):
        full_sync(make_client(h), repo)
    lr = repo.status()["last_run"]
    assert lr["status"] == "error" and lr["request_id"] == "abc123"
    assert repo.get_state("sync_running") == ""  # lock liberado


def test_retry_on_429(monkeypatch):
    monkeypatch.setattr("app.upseller_client.time.sleep", lambda s: None)
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        return httpx.Response(429) if n["i"] < 3 else httpx.Response(200, json=WH)
    assert make_client(h).get_warehouses()["code"] == 0 and n["i"] == 3


def test_search_and_order(repo):
    full_sync(make_client(api_handler([])), repo)
    rows, total = repo.search("REF", order="available", desc=True)
    assert total == 2 and rows[0]["sku"] == "REF-200"
    rows, _ = repo.search("camisetas")  # título (LIKE é case-insensitive para ASCII)
    assert any(r["sku_type"] == "KIT" for r in rows)


def test_rate_limiter_blocks_after_limit(monkeypatch):
    rl = RateLimiter(2)
    slept = []
    monkeypatch.setattr("app.upseller_client.time.sleep", lambda s: (slept.append(s), rl._calls.clear()))
    rl.wait(); rl.wait(); rl.wait()
    assert slept and slept[0] > 0


def test_settings_repr_hides_token():
    assert "tok" not in repr(Settings(client_id="id", api_token="tok"))
