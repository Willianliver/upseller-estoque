"""Cliente httpx para a API aberta do UpSeller (somente os 2 endpoints de leitura de estoque)."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

import httpx

from .config import Settings

log = logging.getLogger(__name__)

EP_WAREHOUSES = "/erp/inventory/getWarehouseList/v1"
EP_WAREHOUSE_SKU = "/erp/inventory/pageWarehouseSku/v1"


class UpSellerError(Exception):
    def __init__(self, message: str, code: Any = None, request_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.request_id = request_id

    def __str__(self) -> str:
        return f"{super().__str__()} (code={self.code}, requestId={self.request_id})"


class RateLimiter:
    """Janela deslizante de 60s: no máximo `per_minute` chamadas."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= 60:
                    self._calls.popleft()
                if len(self._calls) < self.per_minute:
                    self._calls.append(now)
                    return
                sleep_for = 60 - (now - self._calls[0])
            time.sleep(max(sleep_for, 0.05))


class UpSellerClient:
    MAX_RETRIES = 4

    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None):
        self.settings = settings or Settings()
        self.settings.validate()
        self._limiter = RateLimiter(self.settings.rate_limit_per_minute)
        self._http = httpx.Client(
            base_url=self.settings.base_url,
            timeout=30,
            transport=transport,
            headers={
                "X-Upseller-Client-Id": self.settings.client_id,
                "X-Upseller-Api-Token": self.settings.api_token,
                "X-Upseller-Language": self.settings.language,
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._http.close()

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRIES + 1):
            self._limiter.wait()
            try:
                resp = self._http.post(path, json=body)
            except httpx.TransportError as exc:  # rede/timeout
                last_exc = exc
                log.warning("falha de rede em %s (tentativa %d): %s", path, attempt + 1, type(exc).__name__)
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_exc = UpSellerError(f"HTTP {resp.status_code}", resp.status_code)
                    log.warning("HTTP %s em %s (tentativa %d)", resp.status_code, path, attempt + 1)
                else:
                    payload = resp.json()
                    if resp.status_code >= 400 or payload.get("code") not in (0, "0"):
                        err = UpSellerError(
                            str(payload.get("message", "erro")), payload.get("code", resp.status_code), payload.get("requestId")
                        )
                        log.error("erro da API em %s: %s", path, err)
                        raise err
                    return payload
            if attempt < self.MAX_RETRIES:
                time.sleep(min(2**attempt, 30))
        raise UpSellerError(f"falha após {self.MAX_RETRIES + 1} tentativas: {last_exc}")

    def get_warehouses(self, warehouse_type: str = "ALL") -> dict[str, Any]:
        """warehouse_type: ALL, SELF_OPERATED ou THIRD_PARTY."""
        return self._post(EP_WAREHOUSES, {"warehouseType": warehouse_type})

    def page_warehouse_sku(
        self,
        warehouse_ids: list[Any],
        skus: list[str] | None = None,
        page_no: str | int | None = None,
        page_size: int = 20,
        update_time: int | None = None,
    ) -> dict[str, Any]:
        # pageNo é um cursor em texto (conforme o esquema do MCP); omitido na 1ª página
        body: dict[str, Any] = {"warehouseIdList": [str(i) for i in warehouse_ids], "pageSize": page_size}
        if page_no not in (None, ""):
            body["pageNo"] = str(page_no)
        if skus:
            body["skuList"] = skus
        if update_time:
            body["updateTime"] = update_time
        return self._post(EP_WAREHOUSE_SKU, body)
