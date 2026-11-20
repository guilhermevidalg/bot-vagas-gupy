# Fase 6 — GitHub Actions: rodar o bot todo dia sozinho

## Contexto
O bot já funciona de ponta a ponta, mas só roda quando alguém digita o comando no Mac.
A Fase 6 coloca o bot para rodar **sozinho, 1x por dia, nos servidores do GitHub** (de graça
em repositório público), usando os Secrets para o token e salvando o `dados/vagas.db` no
repositório depois de cada execução. Assim o bot "lembra" das vagas de um dia para o outro.

**Pré-requisito:** o PR da Fase 5 ([#4](https://github.com/guilhermevidalg/bot-vagas-gupy/pull/4))
ainda está **aberto**. Fazer o merge antes; depois `git checkout main && git pull` e
`git checkout -b fase-6-actions`.

## O que é o GitHub Actions (resumo)
Um serviço do GitHub que liga uma máquina Linux temporária, executa uma lista de passos
descrita num arquivo YAML em `.github/workflows/` e desliga. Cada arquivo é um **workflow**;
ele roda quando acontece um **gatilho**: um horário (`schedule`, formato cron), um botão
manual (`workflow_dispatch`) ou um push/PR.

## Arquivos novos

### 1. `.github/workflows/bot-vagas.yml` — a execução diária
- **Gatilhos:** `schedule` com cron `17 11 * * *` (todo dia às 11:17 UTC = **08:17 em
  Brasília**; minuto "quebrado" porque às horas cheias o GitHub atrasa) + `workflow_dispatch`
  (botão "Run workflow" para rodar na hora).
- **`permissions: contents: write`**: deixa o workflow fazer commit do banco.
- **`concurrency`**: impede duas execuções ao mesmo tempo mexendo no mesmo banco.
- **`timeout-minutes: 15`**: se travar, para sozinho.
- Passos:
  1. `actions/checkout` (baixa o repositório, incluindo o `dados/vagas.db`).
  2. `actions/setup-python` com Python 3.12 e cache do pip.
  3. `pip install -r requirements.txt`.
  4. `pytest -q`: se algum teste falhar, o bot nem roda.
  5. `python -m bot_vagas.main` com `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` vindos de
     `${{ secrets.... }}`. Sem `.env` aqui: `carregar_env()` não acha o arquivo e usa as
     variáveis do ambiente. Se der erro, o código de saída 1 deixa a execução vermelha.
  6. Commit do banco **só se mudou**: configura o autor como `github-actions[bot]`,
     `git add dados/vagas.db`, commit "Atualiza vagas vistas (AAAA-MM-DD)", `git pull --rebase`
     e `git push`.
- As versões das actions (`checkout`, `setup-python`) serão conferidas na hora com o `gh`,
  usando a versão estável mais recente.

### 2. `.github/workflows/testes.yml` — testes em todo push e PR
Roda o `pytest` em push e pull request. O PR passa a mostrar um ✓ verde (ou ✗ vermelho),
e isso conta pontos num portfólio. Os commits do banco feitos pelo bot **não** disparam esse
workflow (regra do GitHub para commits feitos com o token do próprio Actions), então não
vira um loop.

## Alterações
- `README.md`: selo (badge) com o status do workflow, explicação de como o bot roda e de
  como configurar os Secrets.
- `CLAUDE.md`: regras da Fase 6 e status (todas as fases concluídas).
- `docs/planos/fase-6-actions.md`: cópia deste plano.

## Configuração que é sua (no site do GitHub)
Os Secrets guardam o token cifrado. Nem o código nem o log mostram o valor; o GitHub ainda
troca automaticamente qualquer aparição por `***` no log.
1. Repositório → **Settings** → **Secrets and variables** → **Actions** →
   **New repository secret**.
2. Criar `TELEGRAM_TOKEN` (o token atual) e `TELEGRAM_CHAT_ID` (o número do seu chat).

## Verificação
1. `pytest -v` local: tudo passa.
2. Push da branch + PR: o `testes.yml` roda e o PR mostra ✓.
3. Depois do merge e dos Secrets criados: rodar na hora com
   `gh workflow run bot-vagas.yml` e acompanhar com `gh run watch`.
   Esperado: no Telegram, "🤖 Bot iniciado: N vagas registradas", e no repositório um
   commit do `github-actions[bot]` criando o `dados/vagas.db`.
4. Rodar de novo: chega "Nenhuma vaga nova hoje" (ou poucas vagas) e o commit só aparece se
   houver vaga nova.
5. No dia seguinte, conferir se a execução agendada aconteceu sozinha (aba **Actions**).

## Limites para conhecer
- O horário do `schedule` é aproximado: o GitHub pode atrasar alguns minutos (ou mais).
- Em repositório público, o GitHub **desativa workflows agendados após 60 dias sem
  atividade** no repositório. Se acontecer, chega um e-mail e é só reativar na aba Actions.
