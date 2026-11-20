# Fase 3 — Banco de vagas já vistas (`bot_vagas/banco.py`)

## Contexto
O bot roda 1x por dia e não pode reenviar no Telegram vagas já enviadas. A fase 3 cria a
"memória" do bot: um arquivo SQLite (`dados/vagas.db`) com os ids das vagas já vistas. O
`.gitignore` já tem a exceção `!dados/vagas.db` (o Actions vai commitar esse arquivo na fase 6).
`sqlite3` vem com o Python — nenhuma dependência nova.

## Passo 0 — Limpeza e branch
- Apagar `fase-2-filtros` local (`git branch -d`, que só apaga se já estiver no merge) e
  remota (`git push origin --delete fase-2-filtros`).
- `git checkout -b fase-3-banco` a partir da `main` atualizada.

## Passo 1 — `bot_vagas/banco.py` (novo)
- `CAMINHO_PADRAO = <raiz>/dados/vagas.db` (mesmo padrão de `config.py`).
- Tabela `vagas_vistas`: `id INTEGER PRIMARY KEY` (id da Gupy), `titulo`, `empresa`, `url`,
  `vista_em` (data/hora UTC em texto ISO). Só o `id` é essencial; o resto ajuda a consultar.
- `conectar(caminho=CAMINHO_PADRAO) -> sqlite3.Connection`: cria a pasta se faltar e
  `CREATE TABLE IF NOT EXISTS` (seguro rodar todo dia).
- `esta_vazio(conn) -> bool`: útil para avisar se esquecerem o `--inicializar`.
- `separar_novas(conn, vagas) -> list[Vaga]`: devolve só as que não estão no banco
  (mantém a ordem).
- `registrar(conn, vagas) -> int`: `INSERT OR IGNORE` (repetidas não dão erro), dentro de
  uma transação (`with conn:`); devolve quantas foram gravadas de fato.
- `inicializar(conn, vagas) -> int`: só registra, sem enviar nada — é a lógica da flag
  `--inicializar`.

**Decisões:**
- Grava só as vagas **aceitas pelo filtro** (as que seriam enviadas). Se um dia o filtro
  mudar (ex.: novo estado), vagas antes recusadas aparecem como novas — que é o desejado.
- A ordem certa no `main.py` (fase 5) será: buscar → filtrar → `separar_novas` → **enviar** →
  `registrar`. Registrar só depois do envio dar certo evita "perder" vagas se o Telegram falhar.
- A flag `--inicializar` em si (linha de comando, `argparse`) fica no `main.py` da fase 5,
  junto com `--dry-run`; nesta fase entra a função `inicializar()` que ela vai chamar.

## Passo 2 — `tests/test_banco.py` (novo)
Usando a fixture `tmp_path` do pytest (pasta temporária por teste — nunca toca no
`dados/vagas.db` real):
- `conectar` cria pasta/arquivo/tabela; conectar 2x não dá erro e mantém os dados.
- banco novo está vazio; depois de registrar, não está.
- `separar_novas`: tudo é novo no banco vazio; depois de registrar, só as inéditas voltam.
- `registrar` ignora repetidas (devolve 0 na 2ª vez) e persiste após fechar/reabrir.
- `inicializar` popula o banco e uma busca seguinte com as mesmas vagas não traz novidades.

## Passo 3 — Documentação
`CLAUDE.md`: estrutura (`banco.py`), regras da fase 3 (o que é gravado e a ordem
enviar → registrar), fase 5 ganha a flag `--inicializar`, status da fase 3 marcado.

## Passo 4 — Commit e push
Commit "Fase 3: banco SQLite de vagas já vistas" (sem Co-Authored-By/menção ao Claude) e
`git push -u origin fase-3-banco`.

## Verificação
- `pytest -v` → testes das fases 1–3 passando.
- Teste manual: script no scratchpad que usa um banco temporário, roda busca real (2 termos) →
  filtro → `separar_novas` → `registrar`, e roda de novo para confirmar "0 novas".
