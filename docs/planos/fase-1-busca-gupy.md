# Fase 1 — Estrutura do projeto + módulo que busca vagas na Gupy (versão aprovada com ajustes)

## Contexto
Projeto de portfólio `bot-vagas`: bot diário (GitHub Actions) que busca estágios de TI
na API pública da Gupy, filtra, guarda as vagas já vistas em SQLite e manda as novas no Telegram.
A **fase 1** cobre: estrutura de pastas, configuração e o módulo que **busca** vagas (`gupy.py`),
com testes que simulam a API. Filtro, banco, Telegram e Actions ficam para as próximas fases.

Ambiente: **Python 3.12** (o usuário vai instalar) → sintaxe moderna (`str | None`,
`list[str]`), `tomllib` da biblioteca padrão, sem `from __future__`.

## Estrutura de pastas (✅ = criado na fase 1)
```
bot-vagas/
├── bot_vagas/
│   ├── __init__.py       ✅
│   ├── config.py         ✅ carregar_config() com tomllib
│   ├── gupy.py           ✅ busca, paginação, normalização, deduplicação
│   ├── filtros.py           (fase 2)
│   ├── banco.py             (fase 3)
│   └── telegram.py          (fase 4)
├── dados/
│   └── .gitkeep          ✅ pasta onde ficará dados/vagas.db (commitado pelo Actions)
├── tests/
│   ├── __init__.py       ✅
│   └── test_gupy.py      ✅
├── config.toml           ✅ conteúdo exato fornecido pelo usuário
├── main.py                  (fase 5)
├── .github/workflows/       (fase 6)
├── requirements.txt      ✅ requests, pytest, responses (sem tomli)
├── .env.example          ✅ TELEGRAM_TOKEN= / TELEGRAM_CHAT_ID=
├── .gitignore            ✅ .env, .venv, __pycache__, .pytest_cache, *.db + exceção !dados/vagas.db
└── README.md             ✅ esboço
```

## gupy.py — detalhes
- `URL_API = "https://portal.api.gupy.io/api/v1/jobs"`
- `USER_AGENT = "bot-vagas/1.0 (projeto de portfolio; busca diaria de estagios)"` enviado em
  todas as requisições via `requests.Session` (headers).
- `@dataclass class Vaga`: `id, titulo, empresa, url, cidade: str | None, estado: str | None,
  remota: bool, modelo: str, publicada_em: str | None, termos: list[str]` (default_factory=list).
  - `remota = isRemoteWork is True or workplaceType == "remote"`.
  - `modelo`: "remoto" / "híbrido" / "presencial" / "não informado" a partir de `workplaceType`.
  - propriedade `local_texto`: "Remoto" | "Cidade - Estado" | "Local não informado".
- `_converter(item: dict, termo: str) -> Vaga` — tolera campos ausentes.
- `buscar_vagas(termo, limite=100, max_paginas=3, pausa=1.0, session=None) -> list[Vaga]`
  - Loop: `GET ?jobName=termo&limit=limite&offset=offset`, `timeout=15`, `raise_for_status()`.
  - **`offset += len(pagina)`** (não assume que a API respeita `limit`).
  - Para quando: página vazia, `offset >= pagination.total` (se vier), ou `max_paginas` atingido.
  - `time.sleep(pausa)` entre requisições (não antes da primeira).
  - Log (`logging`) de quantas vagas vieram em cada página.
- `buscar_todos(termos, limite, max_paginas, pausa, session=None) -> tuple[list[Vaga], list[str]]`
  - Para cada termo: tenta `buscar_vagas`; se der exceção (`requests.RequestException`/`ValueError`),
    `logger.error(...)`, adiciona o termo em `termos_com_falha` e continua.
  - Deduplica por `id` num dicionário; se a vaga já existe, **acrescenta o termo** em `vaga.termos`
    (sem repetir).
  - Pausa também entre termos.
  - Retorna `(vagas, termos_com_falha)` → usado depois para o aviso de "busca parcial".

## config.py
- `carregar_config(caminho="config.toml") -> dict` usando `tomllib.load` (arquivo aberto em `"rb"`).

## Testes (tests/test_gupy.py, com `responses`, pausa=0)
1. Conversão de item → `Vaga` (vaga remota com cidade da sede: `remota=True`, `local_texto="Remoto"`).
2. Item sem cidade/estado → `local_texto == "Local não informado"`.
3. Paginação quando a API devolve **menos** que `limit` (ex.: pede 100, vêm 10): offset avança
   10 em 10 — verificado pelos parâmetros das chamadas registradas.
4. Para em página vazia; para em `max_paginas`; para ao atingir `total`.
5. User-Agent presente no cabeçalho.
6. `buscar_todos`: deduplica e junta `termos` da mesma vaga.
7. `buscar_todos`: um termo com HTTP 500 → os outros seguem e o termo aparece em `termos_com_falha`.
8. Carregar o `config.toml` real e checar chaves principais.

## Verificação
1. `python3.12 -m venv .venv && source .venv/bin/activate && pip3 install -r requirements.txt`
2. `pytest -v` → tudo passa, sem internet.
3. Teste manual (chama a API real, 1 termo, mostra vagas por página via log):
   `python3 -c "import logging; logging.basicConfig(level=logging.INFO); from bot_vagas.gupy import buscar_vagas; v=buscar_vagas('estágio TI', max_paginas=2); print(len(v)); print(v[0])"`
4. Ao final, explicar cada arquivo criado e as partes principais do código.

## Anotações para as próximas fases (salvar em memória ao sair do plan mode)
- **Fase 2 (filtros):** normalizar textos (minúsculas, sem acento) antes de comparar;
  "intern"/"internship" como palavra inteira (não casar "internacional"). Localização: remota
  primeiro (aceita de qualquer lugar); senão exige estado em `estados_permitidos`; sem local
  passa com "Local não informado" (se `aceitar_local_nao_informado`).
- **Fase 3 (banco):** `dados/vagas.db` commitado pelo Actions; flag `--inicializar` na primeira
  execução popula o banco sem enviar mensagem.
- Termos que falharam → aviso de busca parcial no Telegram (fase 4/5).
