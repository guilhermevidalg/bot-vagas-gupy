"""Montagem e envio da mensagem de vagas pelo Telegram.

Usa a API HTTP de bots do Telegram (método sendMessage) com o mesmo
`requests` da busca na Gupy. Ligar busca → filtro → banco → envio fica
para o main.py (Fase 5).
"""

import html
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from bot_vagas.gupy import Vaga

# O token entra no meio da URL; por isso a URL NUNCA aparece em logs ou erros
URL_API = "https://api.telegram.org/bot{token}/sendMessage"
LIMITE_CARACTERES = 4096  # tamanho máximo de uma mensagem no Telegram
TIMEOUT_SEGUNDOS = 15
PAUSA_ENTRE_ENVIOS = 1.0  # segundos entre um pedaço e outro da mensagem
# O GitHub Actions roda em UTC; a data da mensagem segue o horário de Brasília
FUSO = ZoneInfo("America/Sao_Paulo")
# Linha em branco entre blocos: também é onde a mensagem pode ser dividida
SEPARADOR = "\n\n"

logger = logging.getLogger(__name__)


class ErroTelegram(Exception):
    """Falha ao falar com o Telegram (a mensagem nunca contém o token)."""


def _data_hoje(agora: datetime | None = None) -> str:
    """Data no formato dd/mm/aaaa, no fuso de São Paulo."""
    agora = agora or datetime.now(FUSO)
    return agora.astimezone(FUSO).strftime("%d/%m/%Y")


def formatar_vaga(vaga: Vaga) -> str:
    """Monta o bloco HTML de uma vaga (título, detalhes e link)."""
    # html.escape troca &, < e > por códigos seguros (ex.: "P&D" -> "P&amp;D")
    titulo = f"<b>{html.escape(vaga.titulo or 'Vaga sem título')}</b>"
    if vaga.eh_banco_talentos:
        titulo += "  🏷 Banco de talentos"

    detalhes = [vaga.empresa, vaga.local_texto]
    # Remota já aparece como "Remoto" no local: não repetimos o modelo
    if not vaga.remota and vaga.modelo != "não informado":
        detalhes.append(vaga.modelo)
    linha_detalhes = " · ".join(html.escape(d) for d in detalhes if d)

    if vaga.url:
        link = f'<a href="{html.escape(vaga.url, quote=True)}">Ver vaga</a>'
    else:
        link = "Link não informado"

    return "\n".join([titulo, linha_detalhes, link])


def _aviso_busca_parcial(termos_com_falha: list[str]) -> str:
    """Aviso de que alguns termos falharam (as vagas deles podem ter faltado)."""
    termos = ", ".join(f'"{html.escape(t)}"' for t in termos_com_falha)
    if len(termos_com_falha) == 1:
        return f"⚠️ Busca parcial: falhou o termo {termos}."
    return f"⚠️ Busca parcial: falharam {len(termos_com_falha)} termos: {termos}."


def montar_mensagem(
    vagas: list[Vaga],
    termos_com_falha: list[str] | None = None,
    agora: datetime | None = None,
) -> str:
    """Monta a mensagem completa do dia (pode passar de 4096 caracteres)."""
    data = _data_hoje(agora)
    blocos: list[str] = []

    if vagas:
        quantidade = len(vagas)
        texto = "vaga nova" if quantidade == 1 else "vagas novas"
        blocos.append(f"🎓 <b>{quantidade} {texto} de estágio</b> — {data}")
        blocos.extend(formatar_vaga(v) for v in vagas)
    else:
        blocos.append(f"📭 Nenhuma vaga nova hoje — {data}")

    if termos_com_falha:
        blocos.append(_aviso_busca_parcial(termos_com_falha))

    return SEPARADOR.join(blocos)


def montar_aviso_falha(erro: Exception | str, agora: datetime | None = None) -> str:
    """Mensagem curta avisando que a execução do dia deu erro."""
    detalhe = html.escape(str(erro))[:500]  # corta erros enormes
    return f"❌ <b>O bot de vagas falhou</b> — {_data_hoje(agora)}\n{detalhe}"


def dividir_mensagem(texto: str, limite: int = LIMITE_CARACTERES) -> list[str]:
    """Divide o texto em pedaços de até `limite` caracteres.

    O corte acontece sempre ENTRE blocos (linhas em branco), para nunca
    quebrar uma tag HTML no meio. Contamos as tags também, então o
    tamanho real exibido fica sempre abaixo do limite (margem de segurança).
    """
    pedacos: list[str] = []
    atual = ""

    for bloco in texto.split(SEPARADOR):
        # Bloco sozinho maior que o limite (muito improvável): corta na marra
        while len(bloco) > limite:
            if atual:
                pedacos.append(atual)
                atual = ""
            pedacos.append(bloco[:limite])
            bloco = bloco[limite:]

        candidato = f"{atual}{SEPARADOR}{bloco}" if atual else bloco
        if len(candidato) <= limite:
            atual = candidato
        else:
            pedacos.append(atual)
            atual = bloco

    if atual:
        pedacos.append(atual)
    return pedacos


def _enviar_pedaco(texto: str, token: str, chat_id: str, http: requests.Session) -> None:
    """Envia UMA mensagem; lança ErroTelegram se algo der errado."""
    try:
        resposta = http.post(
            URL_API.format(token=token),
            json={
                "chat_id": chat_id,
                "text": texto,
                "parse_mode": "HTML",
                # Sem prévia dos links, senão a mensagem fica enorme
                "disable_web_page_preview": True,
            },
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.RequestException as erro:
        # "from None" esconde o erro original, cuja mensagem traz a URL com o token
        raise ErroTelegram(f"falha de conexão com o Telegram ({type(erro).__name__})") from None

    try:
        corpo = resposta.json()
    except ValueError:
        corpo = {}

    if resposta.status_code != 200 or not corpo.get("ok"):
        descricao = corpo.get("description") or f"HTTP {resposta.status_code}"
        raise ErroTelegram(f"o Telegram recusou a mensagem: {descricao}")


def enviar_texto(
    texto: str,
    token: str,
    chat_id: str,
    session: requests.Session | None = None,
    pausa: float = PAUSA_ENTRE_ENVIOS,
) -> int:
    """Divide o texto se preciso e envia cada pedaço. Devolve quantos foram enviados.

    Se qualquer pedaço falhar, lança ErroTelegram (quem chama NÃO deve
    registrar as vagas no banco nesse caso).
    """
    http = session or requests.Session()
    pedacos = dividir_mensagem(texto)

    for indice, pedaco in enumerate(pedacos):
        if indice > 0:
            time.sleep(pausa)  # evita o limite de mensagens por segundo do Telegram
        _enviar_pedaco(pedaco, token, chat_id, http)
        logger.info("Telegram: pedaço %d/%d enviado", indice + 1, len(pedacos))

    return len(pedacos)


def ler_credenciais() -> tuple[str, str]:
    """Lê TELEGRAM_TOKEN e TELEGRAM_CHAT_ID das variáveis de ambiente."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    faltando = [nome for nome, valor in
                (("TELEGRAM_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)) if not valor]
    if faltando:
        raise ErroTelegram(f"variáveis de ambiente não definidas: {', '.join(faltando)}")
    return token, chat_id
