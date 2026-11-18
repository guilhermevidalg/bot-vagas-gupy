"""Testes do módulo telegram.py.

A biblioteca `responses` intercepta os POSTs do `requests`: nenhuma
mensagem chega ao Telegram de verdade.
"""

import json
from datetime import datetime, timezone

import pytest
import responses

from bot_vagas.gupy import TIPO_BANCO_TALENTOS, TIPO_ESTAGIO, Vaga
from bot_vagas.telegram import (
    LIMITE_CARACTERES,
    URL_API,
    ErroTelegram,
    dividir_mensagem,
    enviar_texto,
    formatar_vaga,
    ler_credenciais,
    montar_aviso_falha,
    montar_mensagem,
)

TOKEN = "123456:TOKEN-FALSO"
CHAT_ID = "999"
URL = URL_API.format(token=TOKEN)
# 16/11/2026 às 01:00 em UTC = 15/11/2026 às 22:00 em São Paulo
AGORA_UTC = datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc)


def criar_vaga(id_vaga=1, **extras) -> Vaga:
    """Cria uma Vaga de exemplo; `extras` troca qualquer campo."""
    dados = dict(
        id=id_vaga,
        titulo=f"Estágio em TI {id_vaga}",
        empresa="Empresa X",
        url=f"https://empresax.gupy.io/jobs/{id_vaga}",
        cidade="Rio de Janeiro",
        estado="Rio de Janeiro",
        remota=False,
        modelo="híbrido",
        publicada_em=None,
        tipo=TIPO_ESTAGIO,
    )
    dados.update(extras)
    return Vaga(**dados)


# ---------- formatar_vaga ----------

def test_formatar_vaga_tem_titulo_detalhes_e_link():
    bloco = formatar_vaga(criar_vaga(7))
    assert "<b>Estágio em TI 7</b>" in bloco
    assert "Empresa X · Rio de Janeiro - Rio de Janeiro · híbrido" in bloco
    assert '<a href="https://empresax.gupy.io/jobs/7">Ver vaga</a>' in bloco
    assert "Banco de talentos" not in bloco


def test_formatar_vaga_remota_mostra_remoto_uma_vez_so():
    bloco = formatar_vaga(criar_vaga(remota=True, modelo="remoto"))
    assert "Empresa X · Remoto" in bloco
    assert bloco.lower().count("remoto") == 1


def test_formatar_vaga_sem_modelo_nao_mostra_nao_informado():
    bloco = formatar_vaga(criar_vaga(modelo="não informado"))
    assert "não informado" not in bloco


def test_formatar_vaga_escapa_html():
    bloco = formatar_vaga(criar_vaga(titulo="Estágio P&D <Dados>", empresa="A&B"))
    assert "Estágio P&amp;D &lt;Dados&gt;" in bloco
    assert "A&amp;B" in bloco


def test_formatar_vaga_banco_de_talentos_ganha_etiqueta():
    bloco = formatar_vaga(criar_vaga(tipo=TIPO_BANCO_TALENTOS))
    assert "🏷 Banco de talentos" in bloco


# ---------- montar_mensagem ----------

def test_cabecalho_no_plural_com_data_de_sao_paulo():
    texto = montar_mensagem([criar_vaga(1), criar_vaga(2), criar_vaga(3)], agora=AGORA_UTC)
    # Em UTC já é dia 16, mas em São Paulo ainda é dia 15
    assert texto.startswith("🎓 <b>3 vagas novas de estágio</b> — 15/11/2026")


def test_cabecalho_no_singular():
    texto = montar_mensagem([criar_vaga(1)], agora=AGORA_UTC)
    assert "<b>1 vaga nova de estágio</b>" in texto


def test_sem_vagas_avisa_nenhuma_vaga_nova():
    texto = montar_mensagem([], agora=AGORA_UTC)
    assert "Nenhuma vaga nova hoje" in texto
    assert "Busca parcial" not in texto


def test_aviso_de_busca_parcial():
    texto = montar_mensagem([criar_vaga(1)], ["estágio TI", "estágio BI"], agora=AGORA_UTC)
    assert texto.endswith('⚠️ Busca parcial: falharam 2 termos: "estágio TI", "estágio BI".')


def test_aviso_de_busca_parcial_mesmo_sem_vagas():
    texto = montar_mensagem([], ["estágio TI"], agora=AGORA_UTC)
    assert "Nenhuma vaga nova hoje" in texto
    assert 'falhou o termo "estágio TI"' in texto


def test_aviso_de_falha_escapa_o_erro():
    texto = montar_aviso_falha(ValueError("deu <ruim>"), agora=AGORA_UTC)
    assert "O bot de vagas falhou" in texto
    assert "deu &lt;ruim&gt;" in texto


# ---------- dividir_mensagem ----------

def test_texto_curto_vira_um_pedaco():
    assert dividir_mensagem("oi\n\ntchau") == ["oi\n\ntchau"]


def test_texto_longo_divide_entre_blocos():
    vagas = [criar_vaga(i) for i in range(200)]
    texto = montar_mensagem(vagas, agora=AGORA_UTC)
    assert len(texto) > LIMITE_CARACTERES

    pedacos = dividir_mensagem(texto)
    assert len(pedacos) > 1
    assert all(len(p) <= LIMITE_CARACTERES for p in pedacos)
    # Nenhum bloco foi cortado: juntando os pedaços volta o texto original
    assert "\n\n".join(pedacos) == texto
    # Cada pedaço termina com um link completo (não corta tag no meio)
    assert all(p.endswith("</a>") for p in pedacos)


def test_bloco_maior_que_o_limite_e_cortado_na_marra():
    pedacos = dividir_mensagem("a" * 25, limite=10)
    assert pedacos == ["a" * 10, "a" * 10, "a" * 5]


# ---------- enviar_texto ----------

@responses.activate
def test_enviar_texto_manda_o_post_certo():
    responses.post(URL, json={"ok": True, "result": {}})

    enviados = enviar_texto("<b>oi</b>", TOKEN, CHAT_ID)

    assert enviados == 1
    corpo = json.loads(responses.calls[0].request.body)
    assert corpo == {
        "chat_id": CHAT_ID,
        "text": "<b>oi</b>",
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }


@responses.activate
def test_enviar_texto_longo_faz_varios_posts():
    responses.post(URL, json={"ok": True, "result": {}})
    texto = montar_mensagem([criar_vaga(i) for i in range(200)], agora=AGORA_UTC)

    enviados = enviar_texto(texto, TOKEN, CHAT_ID, pausa=0)

    assert enviados == len(dividir_mensagem(texto)) > 1
    assert len(responses.calls) == enviados


@responses.activate
def test_resposta_ok_false_lanca_erro_sem_token():
    responses.post(URL, status=400, json={"ok": False, "description": "Bad Request: chat not found"})

    with pytest.raises(ErroTelegram) as info:
        enviar_texto("oi", TOKEN, CHAT_ID)

    assert "chat not found" in str(info.value)
    assert TOKEN not in str(info.value)


@responses.activate
def test_erro_de_conexao_lanca_erro_sem_token():
    # Sem resposta registrada, o `responses` simula uma falha de conexão
    with pytest.raises(ErroTelegram) as info:
        enviar_texto("oi", TOKEN, CHAT_ID)

    assert TOKEN not in str(info.value)
    assert info.value.__cause__ is None  # o erro original (com a URL) foi escondido


@responses.activate
def test_falha_no_segundo_pedaco_interrompe_o_envio():
    responses.post(URL, json={"ok": True, "result": {}})
    responses.post(URL, status=429, json={"ok": False, "description": "Too Many Requests"})
    texto = montar_mensagem([criar_vaga(i) for i in range(200)], agora=AGORA_UTC)

    with pytest.raises(ErroTelegram):
        enviar_texto(texto, TOKEN, CHAT_ID, pausa=0)

    assert len(responses.calls) == 2  # parou no pedaço que falhou


# ---------- ler_credenciais ----------

def test_ler_credenciais(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", " abc ")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    assert ler_credenciais() == ("abc", "123")


def test_ler_credenciais_avisa_o_que_falta(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "abc")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(ErroTelegram, match="TELEGRAM_CHAT_ID"):
        ler_credenciais()
