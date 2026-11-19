# bot-vagas

Bot que roda 1x por dia (GitHub Actions), busca vagas de **estágio em TI** na API pública
do portal da Gupy, filtra por palavras-chave e localização, guarda as vagas já vistas em
SQLite e envia as novas no Telegram.

> 🚧 Em construção, feito em fases.

## Status das fases
- [x] Fase 1 — estrutura do projeto e busca de vagas na Gupy (`bot_vagas/gupy.py`)
- [x] Fase 2 — filtros (palavras-chave, palavras excluídas, localização)
- [x] Fase 3 — banco SQLite (`dados/vagas.db`)
- [x] Fase 4 — envio no Telegram (HTML, divisão em 4096 caracteres)
- [x] Fase 5 — `main.py` com `--dry-run` e `--inicializar`
- [ ] Fase 6 — GitHub Actions

## Como rodar localmente
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
pytest -v
```

## Como usar
```bash
python -m bot_vagas.main --dry-run      # mostra a mensagem do dia, sem enviar nem gravar
python -m bot_vagas.main --inicializar  # só registra as vagas atuais no banco
python -m bot_vagas.main                # busca, envia as novas no Telegram e registra
```
Na primeira execução (banco vazio), o bot registra as vagas atuais e envia só um aviso de
"Bot iniciado". A partir daí, envia apenas as vagas novas de cada dia.

## Configuração
- `config.toml`: termos de busca, palavras-chave, palavras excluídas e estados permitidos.
- `.env` (copie de `.env.example`): `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`. Nunca vai para o Git.

Os planos de cada fase ficam em [`docs/planos/`](docs/planos/).
