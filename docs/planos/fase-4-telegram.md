# Fase 4 — Envio pelo Telegram (`bot_vagas/telegram.py`)

> Recriado a partir do plano aprovado (o arquivo original foi sobrescrito pelo plano da Fase 5).

## Contexto
As Fases 1 a 3 já buscam, filtram e separam as vagas novas, mas o bot ainda não avisa ninguém.
A Fase 4 cria o módulo que **monta a mensagem** e **envia para o Telegram**. Ligar tudo
(buscar → filtrar → separar → enviar → registrar) fica para a Fase 5 (`main.py`).

## Como o Telegram funciona (resumo)
- O Telegram tem uma API HTTP para bots. Para mandar uma mensagem, fazemos um POST em
  `https://api.telegram.org/bot<TOKEN>/sendMessage` com `chat_id`, `text` e
  `parse_mode="HTML"`. Usamos o mesmo `requests` da Gupy, sem biblioteca nova.
- A resposta vem em JSON com `"ok": true/false`.
- Limite de **4096 caracteres** por mensagem.
- No modo HTML, os caracteres `<`, `>` e `&` de títulos e nomes de empresas precisam ser
  "escapados" com `html.escape` da biblioteca padrão. Sem isso, "Estágio P&D" quebraria a mensagem.

## Formato da mensagem
```
🎓 3 vagas novas de estágio — 16/11/2026

<b>Estágio em Desenvolvimento</b>
Empresa X · Rio de Janeiro - Rio de Janeiro · híbrido
<a href="https://...">Ver vaga</a>

<b>Banco de Talentos — Tecnologia</b>  🏷 Banco de talentos
Empresa Y · Remoto
<a href="https://...">Ver vaga</a>

⚠️ Busca parcial: falharam 2 termos: "estágio TI", "estágio BI".
```
- Usa `Vaga.local_texto`, `Vaga.modelo` e `Vaga.eh_banco_talentos` (`bot_vagas/gupy.py`).
- Sem vagas novas: "Nenhuma vaga nova hoje" (e o aviso de busca parcial, se houver).

## Funções do `telegram.py`
1. `formatar_vaga(vaga)`: o bloco de uma vaga (com escape de HTML).
2. `montar_mensagem(vagas, termos_com_falha, agora=None)`: cabeçalho + blocos + aviso de
   busca parcial, ou "Nenhuma vaga nova hoje".
3. `dividir_mensagem(texto, limite=4096)`: corta **entre** blocos de vaga (nunca no meio de
   uma tag `<a>`).
4. `montar_aviso_falha(erro)`: "❌ O bot de vagas falhou: …" (usado pela Fase 5).
5. `enviar_texto(texto, token, chat_id, session=None)`: divide e envia cada pedaço, com pausa
   entre os envios e `disable_web_page_preview`.
6. `ler_credenciais()`: lê `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` do ambiente; erro claro se faltar.

**Erros:** resposta de erro (HTTP ou `"ok": false`) vira `ErroTelegram`, e então a Fase 5 não
chama `registrar()`. A mensagem de erro **não inclui a URL**, porque ela contém o token.

## Ajustes aprovados pelo usuário
1. Vaga remota: mostrar "Remoto" uma vez só (sem repetir o modelo).
2. Cabeçalho com singular/plural: "1 vaga nova" / "3 vagas novas".
3. Data no fuso America/Sao_Paulo (`zoneinfo`), porque o Actions roda em UTC.
4. CLAUDE.md: se a mensagem for dividida e um pedaço falhar, nenhuma vaga é registrada →
   pode repetir no dia seguinte (preferimos repetir a perder vagas).
5. Envio real de teste com 3 vagas de exemplo (uma de banco de talentos, uma com "&").

## Testes (`tests/test_telegram.py`, com `responses`)
- Bloco da vaga, escape de HTML, etiqueta de banco de talentos.
- "Nenhuma vaga nova hoje", aviso de busca parcial, singular/plural, fuso de São Paulo.
- `dividir_mensagem`: cada pedaço ≤ 4096, sem cortar blocos.
- `enviar_texto`: corpo do POST, vários pedaços, `"ok": false` / erro de conexão viram
  `ErroTelegram` sem o token.
- `ler_credenciais`: erro quando a variável falta.
