# Guia de instalação (Windows)

## 1. Pré-requisitos
- Python 3.11+ (testado com 3.14, acessível por `py`).
- Credenciais da API: UpSeller → *Plataforma Aberta → API Privada*. Use o **Token de API** (não o Token MCP) e o Client ID.

## 2. Ambiente
```powershell
cd C:\API_developer\upseller-estoque
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.example .env
```
Edite o `.env` no VS Code e preencha `UPSELLER_CLIENT_ID` e `UPSELLER_API_TOKEN`. **Nunca** cole o token em chats nem faça commit do `.env`.

Principais variáveis: `RATE_LIMIT_PER_MINUTE` (60; o plano Profissional permite 100), `SYNC_INTERVAL_MINUTES` (60), `SYNC_WINDOW_START/END` (08:30/16:30), `SYNC_WEEKDAYS` (mon…fri).

## 3. Primeira carga
```powershell
.venv\Scripts\python.exe -m app.cli sync --full
```
Para ~32 mil SKUs são ~329 requisições (~5 min a 60/min). Confira com `python -m app.cli status`.

## 4. Interface web
```powershell
.venv\Scripts\python.exe -m app.web      # http://127.0.0.1:8000
```
Escuta só em `127.0.0.1`. Não exponha na rede sem antes criar autenticação.

**Atalho:** duplo clique em `Abrir Estoque.bat` (na raiz do projeto). Ele inicia a interface sem janela de console, se ainda não estiver rodando, e abre o navegador; rodar de novo não duplica. `Parar Estoque.bat` encerra só a interface (não afeta agendador nem MCP). Para criar um ícone na Área de Trabalho: botão direito em `Abrir Estoque.bat` → *Enviar para → Área de trabalho (criar atalho)*. A porta vem de `WEB_PORT` no `.env`; erros ficam em `logs/web.log`.

## 5. Sincronização automática (Agendador de Tarefas)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\registrar_tarefa.ps1
```
Cria a tarefa **"UpSeller Estoque - Agendador"**, que inicia no logon, sem janela, e sincroniza a cada hora na janela configurada. A 1ª do dia é completa; as demais, incrementais.

Para ligar/desligar: interface web → **⚙ Configurações** → botão do agendamento. O estado fica no banco e vale após reiniciar o computador.

> No terminal do Claude Code (prefixo `!`, que usa Git Bash), escreva o caminho com barra normal: `scripts/registrar_tarefa.ps1`. Com `\` a barra é removida.

Remover a tarefa: `Unregister-ScheduledTask -TaskName "UpSeller Estoque - Agendador" -Confirm:$false`

## 6. Servidor MCP

Ferramentas: `consultar_estoque`, `buscar_sku`, `listar_armazens`, `status_sincronizacao`, `atualizar_cache`. O servidor lê o cache local; não depende do agendador estar rodando.

### 6.1 Claude Code
```powershell
claude mcp add --scope user upseller-estoque -- C:\API_developer\upseller-estoque\.venv\Scripts\python.exe -m app.mcp_server
claude mcp list          # deve mostrar "Connected"
```
Para não duplicar ferramentas, desative o MCP oficial na sessão: `/mcp disable upseller`.

### 6.2 Claude Desktop (conversas gerais fora do Claude Code)
O Desktop tem configuração própria e **não herda** a do Claude Code. No app: *Configurações → Desenvolvedor → Editar configuração* (abre o `claude_desktop_config.json` no local correto) e adicione:
```json
{
  "mcpServers": {
    "upseller-estoque": {
      "command": "C:\\API_developer\\upseller-estoque\\.venv\\Scripts\\python.exe",
      "args": ["-m", "app.mcp_server"]
    }
  }
}
```
Se o arquivo já tiver outros servidores, acrescente só a entrada dentro de `mcpServers`. Feche o Claude Desktop **totalmente** (bandeja do sistema) e abra de novo. O servidor funciona de qualquer pasta, pois o pacote foi instalado em modo editável.

### 6.3 claude.ai no navegador / celular
Conectores do site exigem um servidor MCP **remoto** (URL pública HTTPS com autenticação). Isso significa expor o sistema na internet, o que contraria a regra "somente local". Não está implementado; só seria feito mediante decisão explícita e com autenticação.
