# Fase 5 — `main.py`: ligar tudo (buscar → filtrar → separar → enviar → registrar)

## Contexto
As peças já existem e estão testadas: busca (`gupy.py`), filtro (`filtros.py`), banco
(`banco.py`) e Telegram (`telegram.py`). Falta o "maestro", um programa que chama as peças na
ordem certa, trata os erros e é o comando que o GitHub Actions vai rodar todo dia (Fase 6).

Antes de começar: `git checkout main && git pull` e `git checkout -b fase-5-main`.

## Como vai rodar
```bash
python -m bot_vagas.main              # execução normal (a que o Actions vai usar)
python -m bot_vagas.main --dry-run    # mostra a mensagem no terminal, não envia nem grava
python -m bot_vagas.main --inicializar   # só popula o banco, sem mensagem
```
O `-m` roda um arquivo **de dentro do pacote** `bot_vagas` como programa, então os imports
`from bot_vagas...` funcionam. Opção extra `--banco CAMINHO` (padrão `dados/vagas.db`), útil
para testar com um banco temporário sem mexer no banco de verdade.

## Peças novas

### 1. `carregar_env()` em `bot_vagas/config.py`
Lê o `.env` **pelo Python, como texto** (nunca `source`):
- Ignora linhas vazias e comentários (`#`).
- Corta no primeiro `=` e tira espaços das pontas (o problema do espaço não volta).
- **Não sobrescreve** variáveis que já existem: no Actions os Secrets já vêm como variáveis
  de ambiente e não existe `.env`.
- Sem `.env`: não faz nada. Nunca imprime valores.

### 2. `bot_vagas/main.py`
- `executar(config, conn, dry_run=False, so_inicializar=False) -> int`: o fluxo, devolve o
  código de saída (0 = deu certo, 1 = erro). Recebe `config` e `conn` prontos, para os testes
  usarem um banco temporário.
- `main()`: lê os argumentos (`argparse`, a biblioteca padrão de opções de linha de comando),
  liga o log, chama `carregar_env()` e `carregar_config()`, abre o banco e chama `executar()`.

**Fluxo do `executar()`:**
1. Se não for `--dry-run` nem `--inicializar`: `ler_credenciais()` **primeiro**. Se faltar
   token, o bot falha em 1 segundo, sem gastar ~2 minutos buscando na Gupy.
2. `buscar_todos(...)` com os parâmetros de `[busca]` do `config.toml`.
   **Se todos os termos falharem**, isso é erro (a Gupy caiu ou mudou), não "nenhuma vaga
   nova hoje".
3. `filtrar_vagas(vagas, config)`.
4. `--inicializar`: `inicializar(conn, aceitas)`, mostra quantas registrou e termina.
5. **Banco vazio** (primeira execução): envia só o aviso "🤖 Bot iniciado: N vagas
   registradas. A partir de amanhã você recebe só as novas." e **depois** registra.
   No `--dry-run`, só mostra esse aviso.
6. Caso normal: `separar_novas()` → `montar_mensagem(novas, termos_com_falha)`.
   - `--dry-run`: imprime a mensagem e termina, sem enviar e sem gravar.
   - Senão: `enviar_texto()` e, **só se der certo**, `registrar(conn, novas)`.
7. **Qualquer erro** no caminho: registra no log, tenta mandar `montar_aviso_falha(erro)` no
   Telegram (se houver credenciais e não for dry-run) e devolve 1. Assim o Actions marca a
   execução como falha (fica vermelha). Se até o aviso falhar, só fica no log.

Busca parcial (alguns termos falharam) **não** é erro: envia normalmente, com o aviso ⚠️.

Reaproveita: `buscar_todos` (`gupy.py`), `filtrar_vagas` (`filtros.py`), `conectar`,
`esta_vazio`, `separar_novas`, `registrar`, `inicializar` (`banco.py`), `montar_mensagem`,
`montar_aviso_falha`, `enviar_texto`, `ler_credenciais`, `ErroTelegram` (`telegram.py`).

## Ajustes aprovados pelo usuário
1. **Segurança:** antes de registrar no log ou enviar o aviso de falha, trocar o token por
   `***` em qualquer texto de erro (`esconder_token(texto, token)`). Erros de conexão/timeout
   do `requests` incluem a URL com o token, e o log do Actions é público. Teste específico.
2. **Resumo no log** ao fim de cada execução: vagas buscadas, aceitas pelo filtro, novas,
   enviadas e termos com falha.
3. Salvar este plano em `docs/planos/fase-5-main.md`, mais os anteriores do bot-vagas:
   - Fase 1: `~/.claude/plans/vou-construir-um-projeto-cosmic-wirth.md` → `fase-1-busca-gupy.md`
   - Fase 3: `~/.claude/plans/pasted-content-id-fa31-estamos-no-purring-bentley.md` → `fase-3-banco.md`
   - Fase 4: o arquivo foi sobrescrito por este plano; recriar `fase-4-telegram.md` com o texto
     aprovado (que está na conversa).
   - Fase 2: não há plano salvo. Os outros arquivos de `~/.claude/plans` são do projeto
     automacao-relatorios e ficam de fora.

## Testes (`tests/test_main.py`, nunca chamam Gupy nem Telegram de verdade)
A busca é trocada por uma função falsa (`monkeypatch`), o Telegram é simulado com `responses`
e o banco fica em `tmp_path`.
- Caso normal: 1 vaga já no banco + 1 nova → envia só a nova e registra só ela.
- Sem vagas novas → envia "Nenhuma vaga nova hoje".
- `--dry-run`: imprime a mensagem (`capsys`), nenhum POST, banco intacto.
- `--inicializar`: registra tudo, nenhum POST.
- Banco vazio → envia "Bot iniciado: N vagas" e registra.
- Envio falha → nada registrado, retorno 1.
- Todos os termos falham → aviso de falha enviado, nada registrado, retorno 1.
- Busca parcial → mensagem com aviso ⚠️, retorno 0.
- Sem credenciais → retorno 1 sem chamar a busca.
- `carregar_env`: tira espaços, ignora comentários, não sobrescreve variável existente,
  arquivo ausente não dá erro.

## Arquivos
- Novo: `bot_vagas/main.py`, `tests/test_main.py`.
- Alterar: `bot_vagas/config.py` (`carregar_env`), `CLAUDE.md` (regras da Fase 5, comando
  `python -m bot_vagas.main`, status), `README.md` (como rodar).

## Verificação
1. `.venv/bin/python -m pytest -v`: todos passam.
2. `--dry-run` com a Gupy de verdade e `--banco` apontando para um arquivo temporário: mostra
   o aviso de "Bot iniciado" com o número real de vagas.
3. Execução real com o mesmo banco temporário: chega no Telegram o aviso "Bot iniciado".
   Rodando de novo: chega "Nenhuma vaga nova hoje" (ou poucas vagas). O `dados/vagas.db` de
   verdade **não é criado**: a primeira inicialização real fica para o Actions (Fase 6).
4. Commit "Fase 5: main.py ligando busca, filtro, banco e Telegram", `git push` e PR.
