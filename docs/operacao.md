# Playbook de operação

## Rotina
- Abrir a interface: duplo clique em `Abrir Estoque.bat`.
- O agendador sincroniza sozinho (seg–sex, 08:30–16:30, a cada 60 min). Nada a fazer.
- Para dado fresco de poucos SKUs: interface → lista de SKUs → **Atualizar estes SKUs ao vivo** (até 300), ou no Claude: `atualizar_cache(skus=[...])`.
- Para tudo agora: **Atualizar agora** (interface) ou `python -m app.cli sync`.
- Desligar o agendamento: interface → **⚙ Configurações**.

## Comandos (`.venv\Scripts\python.exe -m app.cli ...`)
| Comando | O que faz |
|---|---|
| `status` | SKUs no cache, idade do dado, última execução e erro |
| `sync` | Automático: completa se a última não foi hoje, senão incremental |
| `sync --full` / `sync --incremental` | Força o modo |
| `sync-skus A B C` | Atualiza só esses SKUs |
| `consultar A B C` | Lê do cache |

## Como funciona a sincronização
- **Completa:** pagina todo o catálogo (cursor `nextPageNo`, 100 por página) e remove do cache SKUs que sumiram. ~329 requisições.
- **Incremental:** pede só o alterado desde a última (`updateTime` em **segundos**, com margem de 10 min). Itens sem `updateTime` (ex.: kits) só entram na completa diária.
- Trava contra execuções simultâneas (expira em 1 h).
- Limite 60/min com janela deslizante; retry com espera exponencial em rede, 429 e 5xx.

## Onde ver erros
- `logs/scheduler.log` (agendador) e a barra de estado da interface.
- Erros da API trazem `code` e **`requestId`**: informe o `requestId` ao suporte do UpSeller.
- Tokens nunca são gravados em log.

## Solução de problemas
| Sintoma | Causa provável / ação |
|---|---|
| "Processo agendador: não detectado" | A tarefa não iniciou. Rode `Start-ScheduledTask -TaskName "UpSeller Estoque - Agendador"` ou faça logon novamente. Confira `logs/scheduler.log`. |
| Nada sincroniza | Agendamento desativado em Configurações; fora da janela/dia útil; ou computador desligado. |
| `Variáveis ausentes no .env` | Preencha `UPSELLER_CLIENT_ID` e `UPSELLER_API_TOKEN`. |
| `code 4001` | Corpo inválido; veja a mensagem. (`warehouseType` é obrigatório no endpoint de armazéns.) |
| Autenticação recusada | Token errado: use o **Token de API**, não o Token MCP; gere de novo no UpSeller. |
| "já existe uma sincronização em andamento" | Aguarde. Se travou, a trava expira em 1 h. |
| SKU "não encontrado" | O SKU não existe no UpSeller (confira se não é ID de anúncio) ou o cache está antigo: atualize ao vivo. |
| Custo/categoria vazios | O cadastro do UpSeller não tem esses dados (~95% / ~93%). |
| Acentos com `�` no terminal | Só exibição do console; use `PYTHONIOENCODING=utf-8`. Os dados estão corretos. |
| MCP não aparece no Claude Code | `claude mcp list`; reabra a sessão. |
| MCP não aparece no Desktop | Fechar totalmente o app (bandeja) e reabrir; validar o JSON. |
| Interface não abre | Rode `Abrir Estoque.bat`; se falhar, veja `logs/web.log`. Porta ocupada: mude `WEB_PORT` no `.env`. |
| Banco corrompido/perdido | Apague `data/estoque.db` e rode `sync --full`. É só cache. |

## Segurança
`.env`, `data/`, `*.db` e `logs/` estão no `.gitignore`. A interface só escuta em `127.0.0.1`. O sistema só lê do UpSeller.
