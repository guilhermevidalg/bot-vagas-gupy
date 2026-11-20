"""Testes do main.py (fluxo completo) e de carregar_env().

A busca na Gupy é trocada por uma função falsa (monkeypatch), o Telegram é
simulado com `responses` e o banco fica numa pasta temporária (tmp_path).
"""

import json
import logging
import os

import pytest
import requests
import responses

from bot_vagas import banco
from bot_vagas.config import carregar_config, carregar_env
from bot_vagas.gupy import TIPO_ESTAGIO, Vaga
from bot_vagas.main import FiltroSegredos, executar
from bot_vagas.telegram import URL_API, esconder_token

TOKEN = "123456:TOKEN-FALSO-COM-MAIS-DE-20-CARACTERES"
CHAT_ID = "999"
URL = URL_API.format(token=TOKEN)


def criar_vaga(id_vaga: int) -> Vaga:
    """Vaga de estágio no RJ: passa no filtro do config.toml."""
    return Vaga(
        id=id_vaga,
        titulo=f"Estágio em TI {id_vaga}",
        empresa="Empresa X",
        url=f"https://empresax.gupy.io/jobs/{id_vaga}",
        cidade="Rio de Janeiro",
        estado="Rio de Janeiro",
        remota=False,
        modelo="presencial",
        publicada_em=None,
        tipo=TIPO_ESTAGIO,
    )


@pytest.fixture
def config():
    return carregar_config()


@pytest.fixture
def conn(tmp_path):
    conexao = banco.conectar(tmp_path / "vagas.db")
    yield conexao  # o teste roda aqui
    conexao.close()


@pytest.fixture
def credenciais(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT_ID)


def trocar_busca(monkeypatch, vagas, termos_com_falha=()):
    """Faz o main usar uma busca falsa; devolve a lista de chamadas feitas."""
    chamadas = []

    def busca_falsa(termos, **kwargs):
        chamadas.append(termos)
        return list(vagas), list(termos_com_falha)

    monkeypatch.setattr("bot_vagas.main.buscar_todos", busca_falsa)
    return chamadas


def textos_enviados() -> list[str]:
    """Textos de todos os POSTs que o 'Telegram' recebeu."""
    return [json.loads(c.request.body)["text"] for c in responses.calls]


def ids_no_banco(conn) -> set[int]:
    return {linha[0] for linha in conn.execute("SELECT id FROM vagas_vistas")}


# ---------- fluxo normal ----------

@responses.activate
def test_envia_so_as_novas_e_registra(monkeypatch, config, conn, credenciais):
    banco.registrar(conn, [criar_vaga(1)])  # a vaga 1 já foi vista
    trocar_busca(monkeypatch, [criar_vaga(1), criar_vaga(2)])
    responses.post(URL, json={"ok": True, "result": {}})

    assert executar(config, conn) == 0

    [texto] = textos_enviados()
    assert "1 vaga nova" in texto
    assert "Estágio em TI 2" in texto
    assert "Estágio em TI 1" not in texto
    assert ids_no_banco(conn) == {1, 2}


@responses.activate
def test_sem_vagas_novas_avisa(monkeypatch, config, conn, credenciais):
    banco.registrar(conn, [criar_vaga(1)])
    trocar_busca(monkeypatch, [criar_vaga(1)])
    responses.post(URL, json={"ok": True, "result": {}})

    assert executar(config, conn) == 0
    assert "Nenhuma vaga nova hoje" in textos_enviados()[0]


@responses.activate
def test_busca_parcial_envia_com_aviso(monkeypatch, config, conn, credenciais):
    banco.registrar(conn, [criar_vaga(1)])
    trocar_busca(monkeypatch, [criar_vaga(2)], termos_com_falha=["estágio TI"])
    responses.post(URL, json={"ok": True, "result": {}})

    assert executar(config, conn) == 0
    assert "Busca parcial" in textos_enviados()[0]
    assert ids_no_banco(conn) == {1, 2}


# ---------- modos especiais ----------

@responses.activate
def test_dry_run_mostra_e_nao_envia_nem_grava(monkeypatch, config, conn, capsys):
    banco.registrar(conn, [criar_vaga(1)])
    trocar_busca(monkeypatch, [criar_vaga(1), criar_vaga(2)])

    assert executar(config, conn, dry_run=True) == 0

    assert "Estágio em TI 2" in capsys.readouterr().out
    assert len(responses.calls) == 0
    assert ids_no_banco(conn) == {1}


@responses.activate
def test_inicializar_so_grava(monkeypatch, config, conn):
    trocar_busca(monkeypatch, [criar_vaga(1), criar_vaga(2)])

    assert executar(config, conn, so_inicializar=True) == 0

    assert len(responses.calls) == 0
    assert ids_no_banco(conn) == {1, 2}


@responses.activate
def test_banco_vazio_envia_aviso_de_inicio_e_registra(monkeypatch, config, conn, credenciais):
    trocar_busca(monkeypatch, [criar_vaga(1), criar_vaga(2), criar_vaga(3)])
    responses.post(URL, json={"ok": True, "result": {}})

    assert executar(config, conn) == 0

    [texto] = textos_enviados()
    assert "Bot iniciado" in texto and "3 vagas registradas" in texto
    assert "Ver vaga" not in texto  # não lista as vagas
    assert ids_no_banco(conn) == {1, 2, 3}


@responses.activate
def test_dry_run_com_banco_vazio_so_mostra_o_aviso(monkeypatch, config, conn, capsys):
    trocar_busca(monkeypatch, [criar_vaga(1)])

    assert executar(config, conn, dry_run=True) == 0

    assert "Bot iniciado" in capsys.readouterr().out
    assert len(responses.calls) == 0
    assert banco.esta_vazio(conn)


# ---------- erros ----------

@responses.activate
def test_envio_falhou_nao_registra(monkeypatch, config, conn, credenciais):
    banco.registrar(conn, [criar_vaga(1)])
    trocar_busca(monkeypatch, [criar_vaga(2)])
    responses.post(URL, status=400, json={"ok": False, "description": "Bad Request"})

    assert executar(config, conn) == 1
    assert ids_no_banco(conn) == {1}  # a vaga 2 continua "nova" para amanhã


@responses.activate
def test_todos_os_termos_falharam_e_erro(monkeypatch, config, conn, credenciais):
    banco.registrar(conn, [criar_vaga(1)])
    trocar_busca(monkeypatch, [], termos_com_falha=config["busca"]["termos"])
    responses.post(URL, json={"ok": True, "result": {}})

    assert executar(config, conn) == 1

    [texto] = textos_enviados()
    assert "O bot de vagas falhou" in texto
    assert "termos de busca falharam" in texto
    assert "Nenhuma vaga nova" not in texto
    assert ids_no_banco(conn) == {1}


@responses.activate
def test_sem_credenciais_falha_sem_buscar(monkeypatch, config, conn):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    chamadas = trocar_busca(monkeypatch, [criar_vaga(1)])

    assert executar(config, conn) == 1
    assert chamadas == []  # nem chegou a buscar
    assert len(responses.calls) == 0


@responses.activate
def test_token_nunca_aparece_no_log_nem_no_aviso(monkeypatch, config, conn, credenciais, caplog):
    # Simula um erro de conexão cuja mensagem traz a URL com o token
    def busca_quebrada(termos, **kwargs):
        raise requests.ConnectionError(f"Max retries exceeded with url: {URL}")

    monkeypatch.setattr("bot_vagas.main.buscar_todos", busca_quebrada)
    responses.post(URL, json={"ok": True, "result": {}})

    with caplog.at_level(logging.INFO):
        assert executar(config, conn) == 1

    [aviso] = textos_enviados()
    assert TOKEN not in aviso and "***" in aviso
    assert TOKEN not in caplog.text and "***" in caplog.text


# ---------- proteção do token ----------

def test_esconder_token_troca_o_token_informado_e_formatos_de_token():
    texto = f"erro em https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert esconder_token(texto, TOKEN) == "erro em https://api.telegram.org/bot***/sendMessage"
    # Mesmo sem saber qual é o token, qualquer coisa com cara de token some
    outro = "9999999:abcdefghijklmnopqrstuvwxyz_123"
    assert esconder_token(f"x {outro} y") == "x *** y"


def test_filtro_de_log_esconde_o_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "abc")  # curto: só o token exato pega
    registro = logging.LogRecord("x", logging.ERROR, __file__, 1, "falhou: %s", ("url/botabc/",), None)

    FiltroSegredos().filter(registro)

    assert registro.getMessage() == "falhou: url/bot***/"


# ---------- resumo no log ----------

@responses.activate
def test_resumo_no_log(monkeypatch, config, conn, credenciais, caplog):
    banco.registrar(conn, [criar_vaga(1)])
    trocar_busca(monkeypatch, [criar_vaga(1), criar_vaga(2)], termos_com_falha=["x"])
    responses.post(URL, json={"ok": True, "result": {}})

    with caplog.at_level(logging.INFO):
        executar(config, conn)

    assert ("Resumo: 2 buscadas, 2 aceitas pelo filtro, 1 novas, 1 enviadas, "
            "1 termos com falha") in caplog.text


# ---------- carregar_env ----------

def test_carregar_env_tira_espacos_e_ignora_comentarios(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    arquivo = tmp_path / ".env"
    arquivo.write_text("# comentário\n\nTELEGRAM_TOKEN= 123:abc \nTELEGRAM_CHAT_ID = \"42\"\n")

    carregar_env(arquivo)

    assert os.environ["TELEGRAM_TOKEN"] == "123:abc"
    assert os.environ["TELEGRAM_CHAT_ID"] == "42"


def test_carregar_env_nao_sobrescreve_variavel_existente(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "do-actions")
    arquivo = tmp_path / ".env"
    arquivo.write_text("TELEGRAM_TOKEN=do-arquivo\n")

    carregar_env(arquivo)

    assert os.environ["TELEGRAM_TOKEN"] == "do-actions"


def test_carregar_env_sem_arquivo_nao_da_erro(tmp_path):
    carregar_env(tmp_path / "nao-existe.env")  # não deve lançar exceção
