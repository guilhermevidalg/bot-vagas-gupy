# CLAUDE.md — bot-vagas

Bot que roda 1x por dia (GitHub Actions), busca vagas de estágio em TI na Gupy, filtra por
palavras-chave e localização, guarda as vagas já vistas em SQLite e envia as novas numa única
mensagem no Telegram (HTML, link "Ver vaga").

O projeto é feito **em fases, uma por vez**. Antes de implementar cada fase, explicar o plano
em linguagem simples; depois, explicar as partes principais do código.

## Comandos
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip3 install -r requirements.txt
pytest -v                    # testes (nunca chamam a Gupy de verdade)
python -m bot_vagas.main --dry-run   # mostra a mensagem do dia sem enviar nem gravar
python -m bot_vagas.main             # execução normal (a do Actions)
```

## Convenções
- Python **3.12**: sintaxe moderna (`str | None`, `list[str]`), `tomllib` da biblioteca padrão,
  sem `from __future__`.
- Comentários e mensagens em português do Brasil.
- Configuração (termos, palavras-chave, palavras excluídas, estados) fica em `config.toml`,
  nunca fixa no código.
- Segredos (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`) só via variáveis de ambiente: `.env` local
  (fora do Git) e GitHub Secrets no Actions. Manter `.env.example` atualizado.
- O `.env` é lido só pelo Python (`carregar_env()`). **Nunca** usar `source .env` no terminal:
  com espaço depois do `=`, o shell executa o valor e mostra o token no erro.
- Planos de cada fase ficam em `docs/planos/`.
- Testes com pytest + `responses` (simula a API). Toda funcionalidade nova ganha teste.
- Tudo gratuito; repositório público.
- Commits sem `Co-Authored-By` nem menção ao Claude. Fazer `git push` logo após cada commit.

## API da Gupy
- Endpoint: `https://portal.gupy.io/api/job-search/jobs` (o antigo
  `portal.api.gupy.io/api/v1/jobs` responde 404). Parâmetros: `jobName`, `limit`, `offset`.
- Resposta: `data` (lista de vagas) + `pagination` (`limit`, `offset`, `total`).
- Sempre usar o User-Agent próprio do bot (`USER_AGENT` em `gupy.py`); **nunca imitar navegador**.
- Paginação: `offset += len(pagina)` (não assumir que `limit` é respeitado); parar em página
  vazia, ao atingir `total` ou em `max_paginas`. Pausa entre requisições (`pausa_segundos`).
- Campos usados: `id`, `name`, `careerPageName`, `jobUrl`, `city`, `state`, `workplaceType`
  (`"on-site"`, `"hybrid"`, `"remote"`), `type`, `publishedDate`.
  - Não existe mais `isRemoteWork`: remota = `workplaceType == "remote"`.
  - `state` vem por extenso ("Rio de Janeiro") e às vezes `""` → tratar como ausente.
  - `type == "vacancy_type_internship"` marca estágio (`Vaga.eh_estagio`).
  - `type == "vacancy_type_talent_pool"` marca banco de talentos (`Vaga.eh_banco_talentos`).

## Estrutura
- `bot_vagas/config.py` — `carregar_config()` e `carregar_env()` (lê o `.env` como texto,
  tira espaços, não sobrescreve variáveis que já existem).
- `bot_vagas/gupy.py` — `Vaga` (dataclass), `buscar_vagas()` (um termo, paginado) e
  `buscar_todos()` → `(vagas, termos_com_falha)`. Deduplica por `id`; `Vaga.termos` guarda
  todos os termos que encontraram a vaga. Um termo com erro não interrompe os outros.
- `bot_vagas/filtros.py` — `normalizar()`, `contem_palavra()`, `passa_palavras()`,
  `passa_localizacao()` e `filtrar_vagas(vagas, config)`.
- `bot_vagas/banco.py` — `conectar()`, `esta_vazio()`, `separar_novas()`, `registrar()` e
  `inicializar()`. Tabela `vagas_vistas` (`id` da Gupy como chave).
- `bot_vagas/telegram.py` — `formatar_vaga()`, `montar_mensagem()`, `montar_aviso_falha()`,
  `dividir_mensagem()`, `enviar_texto()`, `ler_credenciais()` e `esconder_token()`. Erros
  viram `ErroTelegram`.
- `bot_vagas/main.py` — `executar(config, conn, dry_run, so_inicializar)` (devolve 0 ou 1) e
  `main()` (argparse: `--dry-run`, `--inicializar`, `--banco`). Rodar com
  `python -m bot_vagas.main`.
- `dados/vagas.db` — banco SQLite **commitado** pelo Actions (exceção no `.gitignore`).
- `.github/workflows/bot-vagas.yml` — execução diária + botão manual; commita o banco.
- `.github/workflows/testes.yml` — `pytest` em todo push na main e em todo PR.

## Regras de filtro (Fase 2, implementadas)
- Normalizar textos antes de comparar (minúsculas, sem acento).
- Todas as palavras (chave e excluídas) comparadas como palavra inteira, aceitando plural
  com "s" ("intern" não casa "internacional"; "estagio" casa "estágios").
- Aceitar a vaga se `eh_estagio` **ou** se o título tiver uma palavra-chave; descartar se
  tiver palavra excluída.
- Localização: checar **remota primeiro** (aceita de qualquer lugar, pois pode vir com a
  cidade da sede); senão, exige estado em `estados_permitidos`; sem local informado passa
  com "Local não informado" (se `aceitar_local_nao_informado`).
- Banco de talentos: não tem o tipo estágio, então passa se o título tiver palavra-chave;
  fica marcado por `eh_banco_talentos`.

## Regras do banco (Fase 3, implementadas)
- Grava só as vagas **aceitas pelo filtro**; se o filtro mudar, vagas antes recusadas aparecem
  como novas (desejado).
- `registrar()` só **depois** do envio no Telegram dar certo; se o envio falhar, as vagas
  continuam novas e saem na próxima execução.
- `INSERT OR IGNORE`: registrar a mesma vaga duas vezes não dá erro.

## Regras do Telegram (Fase 4, implementadas)
- API `sendMessage` via `requests`, `parse_mode="HTML"`, sem prévia de links. Títulos,
  empresas e erros passam por `html.escape` ("P&D" → "P&amp;D").
- Cada vaga: título em negrito (+ "🏷 Banco de talentos" se `eh_banco_talentos`), linha
  "empresa · local · modelo" e link "Ver vaga". Vaga remota mostra "Remoto" uma vez só
  (sem repetir o modelo); modelo "não informado" não aparece.
- Cabeçalho com singular/plural ("1 vaga nova" / "3 vagas novas") e data no fuso
  `America/Sao_Paulo` (o Actions roda em UTC). Sem vagas: "Nenhuma vaga nova hoje".
  Aviso de busca parcial quando houver `termos_com_falha`.
- Mensagens acima de 4096 caracteres são divididas **entre** blocos (nunca no meio de uma
  tag), com pausa entre os envios.
- Se **qualquer** pedaço falhar, `enviar_texto()` lança `ErroTelegram` e nenhuma vaga deve ser
  registrada: os pedaços já entregues se repetem no dia seguinte. Preferimos repetir a perder vagas.
- O token fica na URL da API, então a URL **nunca** aparece em erros ou logs (`from None`
  esconde a exceção original do `requests`).

## Regras do main (Fase 5, implementadas)
- Ordem: credenciais → buscar → filtrar → `separar_novas` → enviar → `registrar` (só se o
  envio der certo). Credenciais primeiro: sem token, falha antes de gastar minutos na Gupy.
- `--dry-run` imprime a mensagem sem enviar nem gravar; `--inicializar` só popula o banco.
  Os dois não podem ser usados juntos.
- Banco vazio: envia só "🤖 Bot iniciado: N vagas registradas..." e depois registra.
- Busca parcial não é erro (mensagem sai com ⚠️). **Todos** os termos falhando é erro.
- Qualquer erro: log + aviso de falha no Telegram + código de saída 1 (Actions fica vermelho).
- **Token nunca no log:** todo texto de erro passa por `esconder_token()` (troca por `***`), e
  o `FiltroSegredos` faz o mesmo em toda mensagem de log. O log do Actions é público.
- No fim de cada execução, o log mostra o resumo: buscadas, aceitas, novas, enviadas e termos
  com falha.

## Regras do GitHub Actions (Fase 6, implementadas)
- `bot-vagas.yml`: cron `17 11 * * *` (08:17 em Brasília; minuto quebrado para fugir do
  congestionamento das horas cheias) + `workflow_dispatch` para rodar manualmente.
- Roda os testes antes do bot; se falharem, o bot não roda.
- Secrets `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` viram variáveis de ambiente (não há `.env`).
- `permissions: contents: write` e `concurrency` (nunca duas execuções juntas).
- Commit do `dados/vagas.db` só se mudou, como `github-actions[bot]`, com `git pull --rebase`
  antes do push. Commits feitos pelo Actions não disparam outros workflows (sem loop).
- Python 3.12, `actions/checkout@v7` e `actions/setup-python@v7`.
- Workflows agendados são desativados após 60 dias sem atividade no repositório.

## Status
- [x] Fase 1 — estrutura + busca na Gupy
- [x] Fase 2 — filtros (palavras-chave, localização, banco de talentos)
- [x] Fase 3 — banco SQLite de vagas já vistas
- [x] Fase 4 — envio pelo Telegram
- [x] Fase 5 — `main.py` ligando tudo
- [x] Fase 6 — GitHub Actions (execução diária)
