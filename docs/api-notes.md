# Notas da API UpSeller (mapeadas na Fase 2, 2026-11-05)

Fixtures sanitizadas em `tests/fixtures/` (`warehouses.json`, `warehouse_sku.json`).

## `POST /erp/inventory/getWarehouseList/v1`
Corpo: `{"warehouseType": "ALL" | "SELF_OPERATED" | "THIRD_PARTY"}` (**obrigatório**; sem ele: code 4001).
Resposta: `data` é uma **lista** de armazéns. Campos úteis: `warehouseId` (texto), `warehouseName`, `warehouseType`, `isDefault`.
A conta tem 1 armazém (`My Warehouse`, SELF_OPERATED).

## `POST /erp/inventory/pageWarehouseSku/v1`
Corpo: `warehouseIdList` (lista de textos, 1–100), `skuList` (opcional), `pageSize` (1–100), `pageNo`, `updateTime` (inteiro, opcional).
- **`pageNo` é um cursor em texto**: omitir na 1ª página e usar `data.nextPageNo` nas seguintes. Não é número de página.
- Resposta: `data.skuList[]`, `data.nextPageNo`, `data.hasMore`, `data.totalCount` (hoje 32.762).
- Cada item: `skuId`, `sku`, `skuTitle`, `skuType` (`SKU`/`KIT`), `isGroup`, `categoryId`, `categoryName`, `unitCost`, `subTotal`, `minStock`, `maxStock`, `shelfNumber`, `warehouseId`, `warehouseName`, `createTime`, `updateTime`, `up_info`.
- `up_info`: `onHand`, `allocated`, `available`, `inTransit`, `inTransitPurchase`, `inTransitTransfer`.
- `skuList` vazio ou ausente retorna o catálogo todo. SKU inexistente apenas não aparece (sem erro).

## Armadilhas
- `createTime`/`updateTime` do item misturam **segundos** (ex.: 1793284033) e **milissegundos** (ex.: 1792758287545) e podem ser `null`. Normalizar na leitura.
- Em kits (`skuType=KIT`), `allocated`, `inTransit*` podem ser `null`.
- `unitCost` pode ser `null` (SKUs simples de teste) ou `0.0`.
- Unidade de `updateTime` do **filtro** ainda não validada (provável milissegundos). Validar antes de usar na sincronização incremental.

## Mapeamento para as colunas pedidas
| Coluna da planilha | Campo da API |
|---|---|
| Código do Produto | `skuId` (a confirmar com o usuário) |
| SKU | `sku` |
| Nome do Produto | `skuTitle` |
| Categorias | `categoryName` |
| Status da Venda | **não disponível** neste endpoint |
| Custo de Compra | `unitCost` (pode vir nulo) |
| Armazém | `warehouseName` |
| Estoque | `up_info.onHand`, `allocated`, `available` |
