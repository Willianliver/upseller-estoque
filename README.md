# upseller-estoque

Sistema local de consulta de estoque do UpSeller. Busca os dados pela API, guarda num cache SQLite e entrega por três caminhos que usam o mesmo núcleo:

- **Interface web** local (`http://127.0.0.1:8000`): busca por SKU/nome ou lista colada, filtro por armazém, ordenação, exportação XLSX.
- **Servidor MCP** (`app.mcp_server`): o Claude consulta o estoque com uma chamada de ferramenta, sem montar requisições.
- **CLI** (`app.cli`) e **agendador** (`app.scheduler`): manutenção e sincronização automática, sem nenhuma sessão de IA aberta.

```
UpSeller API ← httpx (limite 60/min, retry) ← núcleo (sync + SQLite) ← web | CLI | MCP | agendador
```

Somente leitura: usa apenas `getWarehouseList` e `pageWarehouseSku`. Credenciais só no `.env`.

## Início rápido (Windows)
Veja [docs/instalacao.md](docs/instalacao.md). Em resumo:
```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.example .env        # preencher UPSELLER_CLIENT_ID e UPSELLER_API_TOKEN
.venv\Scripts\python.exe -m app.cli sync --full     # carga inicial (~5 min para 32 mil SKUs)
.venv\Scripts\python.exe -m app.web                 # interface
```

## Documentação
| Arquivo | Conteúdo |
|---|---|
| [docs/instalacao.md](docs/instalacao.md) | Instalação, agendamento no Windows, registro do MCP (Claude Code e Claude Desktop) |
| [docs/operacao.md](docs/operacao.md) | Rotina diária, comandos, solução de problemas |
| [docs/api-notes.md](docs/api-notes.md) | Campos e armadilhas da API do UpSeller |
| [docs/decisoes.md](docs/decisoes.md) | Decisões, desvios e marcos do projeto |

## Testes
```powershell
.venv\Scripts\python.exe -m pytest -q     # usa fixtures; não chama a API real
```

## Limitações conhecidas
- Sem "Status da Venda" (o endpoint não fornece).
- ~95% dos SKUs vêm sem custo e ~93% sem categoria no cadastro do UpSeller.
- Sincroniza só com o computador ligado (janela seg–sex, 08:30–16:30, configurável no `.env`).
