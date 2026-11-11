"""Teste da Fase 2: 2 chamadas (armazéns + 5 SKUs). Uso: python scripts/probe_api.py <pasta_saida>"""
import json, sys
from pathlib import Path
from app.upseller_client import UpSellerClient, UpSellerError

SKUS = [
    "REF-121",
    "11738377081652217455738277014426453615",
    "KIT3-(TRD-E00005-ATE-QUE-ELE-VENHA-PTO-M)+(TRD-E00006-EIS-ME-AQUI-MAR-M)+(TRD-E00007-FE-BCO-M)",
    "REF-200",
    "1738378449532388975",
]
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
c = UpSellerClient()
try:
    w = c.get_warehouses()
    (out / "warehouses.json").write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ARMAZENS:", json.dumps(w, ensure_ascii=False)[:1500])
    data = w.get("data")
    items = data if isinstance(data, list) else (data or {}).get("list") or (data or {}).get("warehouseList") or []
    print("n_armazens:", len(items), "| chaves do 1o:", list(items[0].keys()) if items else None)
    ids = [i.get("warehouseId", i.get("id")) for i in items]
    print("ids:", ids)
    r = c.page_warehouse_sku(ids, skus=SKUS, page_size=20)
    (out / "sku_response.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SKUS:", json.dumps(r, ensure_ascii=False)[:4000])
except UpSellerError as e:
    print("ERRO API:", e)
finally:
    c.close()
