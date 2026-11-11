# Decisões do projeto

## 2026-11-05 — Fase 1 (Clarificação)

| Tema | Decisão |
|---|---|
| Volume | ~32 mil SKUs, com previsão de crescimento |
| Armazéns | 1 |
| Frequência | De hora em hora; "tempo real" só por consulta ao vivo de SKUs específicos |
| Janela de sincronização | Seg–sex, 08:30–16:30 (ideal seria rodar sem depender do computador ligado; ver pendência) |
| Plano UpSeller | Profissional (limite da API: 100/min; configuramos 60/min por segurança) |
| Usuários | Só o proprietário |
| Ambiente | Local (Windows), interface em 127.0.0.1 |
| Exportação | XLSX |
| Pilha | Python, FastAPI + Jinja2/HTMX, httpx, SQLite, SDK `mcp` (FastMCP), openpyxl, pytest |
| Credenciais | Client ID e Token de API já gerados; vão só no `.env` |
| Repositório | Git inicializado (branch `main`), `.gitignore` e `.env.example` criados antes do 1º commit |

### Colunas desejadas na interface
Código do Produto; SKU; Nome do Produto; Categorias; Status da Venda; Custo de Compra; Armazém (+ estoque).
Só as que a API devolver. **Mapear na Fase 2**; os campos ausentes serão listados no relatório.

### Cálculo de carga (estimativa)
- 32 mil SKUs ÷ 100 por página = ~320 requisições para uma carga completa.
- A 60/min, são ~6 minutos. Uma sincronização completa por hora cabe no limite.
- Sincronização incremental (`updateTime`) deve reduzir isso a poucas requisições por ciclo.
- Conclusão: consulta de hora em hora é viável. Tempo real total não é necessário; para SKUs específicos usamos consulta ao vivo (`skuList`).

### Pendências
1. **Python:** o ambiente tem Python 3.14 (via `py`, o comando `python` não está no PATH). Atende ao requisito 3.11+. Se alguma dependência não suportar 3.14, avaliar instalar 3.12/3.13.
2. **Rodar sem o computador ligado:** exigiria servidor/nuvem. Decisão atual: local, com janela 08:30–16:30. Reavaliar se necessário.
3. **Colunas Código do Produto, Categorias, Status da Venda e Custo de Compra:** a API de estoque pode não retornar todas. Se não retornar, avaliar com o usuário outra fonte (ex.: outros endpoints) antes de fazer qualquer coisa fora dos dois endpoints autorizados.

## 2026-11-05 — Fase 2 (Preparação e teste)

- Cliente `app/upseller_client.py` (httpx, limite de taxa em janela de 60s, retry com backoff para rede/429/5xx) e `app/config.py` criados. Autenticação validada.
- Teste com 5 SKUs: 3 encontrados (`REF-121`, `REF-200`, o KIT3); 2 **não encontrados** (`11738377081652217455738277014426453615`, `1738378449532388975`) — consultados também isoladamente, `totalCount: 0`. Hipótese: são IDs de anúncio/produto de marketplace e não SKU. **Aguardando confirmação do usuário.**
- Catálogo total: 32.762 registros (1 armazém). Paginação por **cursor** (`nextPageNo`), confirmada com `pageSize=2`.
- Esquema do MCP oficial consultado só para ler a definição das ferramentas (nenhum dado foi varrido por ele).
- Campos mapeados em `docs/api-notes.md`. **"Status da Venda" não existe neste endpoint.** "Código do Produto" provavelmente é `skuId` (a confirmar).
- Erro inicial 4001 (`warehouseType` ausente) resolvido; requestIds de erro ficam nos logs.
- Pendente: validar unidade do filtro `updateTime` antes da sincronização incremental.

## 2026-11-05 — Fase 4 (Execução)

- **Validação (Fase 3):** usuário conferiu os 3 SKUs encontrados com o painel; aprovado. Os 2 SKUs "não encontrados" seguem sem explicação (provável ID de anúncio).
- **`updateTime` (filtro):** unidade = **segundos**; milissegundos devolvem 0. Semântica "alterado desde". Itens com `updateTime` nulo (ex.: kits) não aparecem no incremental.
- **Estratégia de sincronização:** 1ª do dia = carga completa (pega nulos e remove SKUs apagados); demais = incremental com margem de 10 min. `smart_sync` decide sozinho. Trava via `sync_state.sync_running` (expira em 1 h).
- **Colunas:** "Código do Produto" = `skuId`; "Status da Venda" **omitida** (não existe no endpoint) até o usuário decidir.
- **mcp fixado em `<2`:** a 2.x renomeou `FastMCP` para `MCPServer`; usamos a 1.x estável.
- **Interface web:** FastAPI + Jinja2 em HTML puro (sem HTMX, não foi necessário). Host fixo 127.0.0.1.
- **MCP:** 5 ferramentas, ~400 tokens de definição; saída tabular TSV, limite de 100 linhas com `truncado`.
- **Agendador:** `python -m app.scheduler`, janela seg–sex 08:30–16:30, a cada 60 min, log em `logs/scheduler.log`.
- Testes: 23, todos com fixtures (sem chamar a API real).

### Marco: carga completa real (2026-11-05)
- 32.762 SKUs em 329 requisições, 305 s, `removed=0`; bate com `totalCount`. Banco: 15 MB.
- Incremental real: 0 linhas / 2 requisições (nada alterado). Web: consulta 0,06–0,08 s; XLSX completo 7 s.
- **Qualidade dos dados no UpSeller (via API):** 31.241 SKUs sem `unitCost` (95%), 30.514 sem categoria (93%), 1.521 kits (todos com custo 0). 27.673 SKUs com estoque disponível > 0. Colunas "Custo" e "Categorias" ficarão majoritariamente vazias; é limitação do cadastro, não do sistema.

### Marco: MCP registrado e interruptor do agendamento (2026-11-05)
- MCP próprio registrado (`claude mcp add --scope user upseller-estoque ...`); `claude mcp list` mostra "Connected". O MCP oficial segue ativo até o usuário rodar `/mcp disable upseller` (comando de sessão, o Claude não executa).
- **Interruptor do agendamento:** `sync_state.scheduler_enabled` no SQLite (persistente; padrão ativado). Tela `/config` com botão Ativar/Desativar. O agendador lê o valor a cada ciclo de 30 s e grava `scheduler_heartbeat`; desativado = nunca sincroniza, mesmo após reiniciar o PC. "Atualizar agora" continua funcionando manualmente.
- **Tarefa do Windows:** `scripts/registrar_tarefa.ps1` criado (inicia `pythonw -m app.scheduler` ao logon). A execução pelo Claude foi **bloqueada pelo classificador de permissões**; não foi contornada. Usuário executa manualmente.
- Testes: 26 (inclui persistência do interruptor e "desativado nunca sincroniza").

### Marco: agendador ativo e Fase 5 (2026-11-05)
- Tarefa "UpSeller Estoque - Agendador" registrada pelo usuário (`!` no Claude Code, caminho com `/` por causa do Git Bash) e iniciada; 1ª sincronização automática às 11:46 ok (incremental, 0 linhas, 2 req).
- MCP oficial `upseller` desabilitado pelo usuário.
- **Git adiado** pelo usuário para uma próxima fase.
- Acesso fora do Claude Code: Claude Desktop instalado (MSIX), ainda **sem** `claude_desktop_config.json`. Caminho recomendado: *Configurações → Desenvolvedor → Editar configuração*. Servidor validado rodando de outra pasta. claude.ai web/celular exigiria MCP remoto exposto na internet: **não implementado** (contraria "somente local").
- Docs criados: README, `docs/instalacao.md`, `docs/operacao.md`.

### Marco: MCP validado no Claude Desktop (2026-11-05)
- Config em `%LOCALAPPDATA%\Claude-Data\claude_pzs8sxrjxfjjc\claude_desktop_config.json` (app MSIX; o "Editar configuração" abre o caminho certo). O Desktop só lê a configuração ao iniciar e conversas antigas não enxergam servidores novos: **fechar pela bandeja, reabrir e usar conversa nova**.
- Handshake stdio validado (5 ferramentas) e consulta real pelo Desktop confirmada pelo usuário (SKUs de teste retornaram corretamente).
- `REF-270` não existe como SKU exato; há 55 variações `KIT2-REF-270-...`. Para códigos parciais usar `buscar_sku`.
- Critério "consulte o estoque do SKU X = uma chamada de ferramenta": atendido.
- Atalhos `Abrir Estoque.bat` / `Parar Estoque.bat` criados (2026-11-05). `app.web` redireciona stdout/stderr para `logs/web.log` quando roda sem console (pythonw), pois o uvicorn exige stderr. Testado: início, re-execução sem duplicar e parada.

## 2026-11-05 — Encerramento da sessão
- Atalhos `.bat` validados pelo usuário (iniciar e parar).
- `CLAUDE.md` ganhou a seção 9 (estado atual, como retomar, armadilhas, pendências). Git segue pendente por decisão do usuário.
