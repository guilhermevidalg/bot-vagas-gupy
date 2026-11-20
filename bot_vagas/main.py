"""Programa principal do bot: busca → filtra → separa as novas → envia → registra.

Como rodar (na raiz do projeto):
    python -m bot_vagas.main                # execução normal (a do GitHub Actions)
    python -m bot_vagas.main --dry-run      # só mostra a mensagem, não envia nem grava
    python -m bot_vagas.main --inicializar  # só registra as vagas atuais no banco
"""

import argparse
import logging
import os
import sqlite3
import sys
import traceback
from pathlib import Path

from bot_vagas import banco
from bot_vagas.config import carregar_config, carregar_env
from bot_vagas.filtros import filtrar_vagas
from bot_vagas.gupy import buscar_todos
from bot_vagas.telegram import (
    ErroTelegram,
    enviar_texto,
    esconder_token,
    ler_credenciais,
    montar_aviso_falha,
    montar_mensagem,
)

logger = logging.getLogger("bot_vagas.main")


class ErroBusca(Exception):
    """Todos os termos de busca falharam: a Gupy caiu ou mudou a API."""


class FiltroSegredos(logging.Filter):
    """Filtro de log que esconde o token em QUALQUER mensagem, de qualquer módulo."""

    def filter(self, record: logging.LogRecord) -> bool:
        mensagem = record.getMessage()  # junta o texto com os argumentos (%s)
        record.msg = esconder_token(mensagem, os.environ.get("TELEGRAM_TOKEN"))
        record.args = ()
        return True  # True = a mensagem continua sendo registrada


def montar_aviso_inicio(quantidade: int) -> str:
    """Mensagem da primeira execução (banco vazio)."""
    texto = "vaga registrada" if quantidade == 1 else "vagas registradas"
    return (
        f"🤖 <b>Bot iniciado</b>: {quantidade} {texto}. "
        "A partir de amanhã você recebe só as novas."
    )


def _buscar(config: dict) -> tuple[list, list[str]]:
    """Busca com os parâmetros do config.toml; erro se TODOS os termos falharem."""
    cfg = config["busca"]
    termos = cfg["termos"]
    vagas, termos_com_falha = buscar_todos(
        termos,
        limite=cfg.get("limite_por_pagina", 100),
        max_paginas=cfg.get("max_paginas", 3),
        pausa=cfg.get("pausa_segundos", 1),
    )
    if termos and len(termos_com_falha) == len(termos):
        raise ErroBusca(f"todos os {len(termos)} termos de busca falharam")
    return vagas, termos_com_falha


def executar(
    config: dict,
    conn: sqlite3.Connection,
    dry_run: bool = False,
    so_inicializar: bool = False,
) -> int:
    """Roda o fluxo do dia. Devolve 0 se deu certo e 1 se deu erro."""
    resumo = {"buscadas": 0, "aceitas": 0, "novas": 0, "enviadas": 0, "termos_com_falha": 0}
    token = chat_id = None

    try:
        # 1. Credenciais primeiro: sem token, falha na hora (sem buscar à toa)
        if not dry_run and not so_inicializar:
            token, chat_id = ler_credenciais()

        # 2. Buscar e 3. filtrar
        vagas, termos_com_falha = _buscar(config)
        resumo["buscadas"] = len(vagas)
        resumo["termos_com_falha"] = len(termos_com_falha)
        aceitas = filtrar_vagas(vagas, config)
        resumo["aceitas"] = len(aceitas)

        # 4. --inicializar: só grava no banco
        if so_inicializar:
            gravadas = banco.inicializar(conn, aceitas)
            print(f"Banco inicializado: {gravadas} vagas registradas.")
            return 0

        # 5. Primeira execução (banco vazio): aviso em vez de centenas de vagas
        if banco.esta_vazio(conn):
            aviso = montar_aviso_inicio(len(aceitas))
            if dry_run:
                print(aviso)
                return 0
            enviar_texto(aviso, token, chat_id)
            banco.inicializar(conn, aceitas)  # só depois do envio dar certo
            return 0

        # 6. Caso normal: só as vagas novas
        novas = banco.separar_novas(conn, aceitas)
        resumo["novas"] = len(novas)
        mensagem = montar_mensagem(novas, termos_com_falha)
        if dry_run:
            print(mensagem)
            return 0

        enviar_texto(mensagem, token, chat_id)
        banco.registrar(conn, novas)  # só depois do envio dar certo
        resumo["enviadas"] = len(novas)
        return 0

    except Exception as erro:
        # 7. Qualquer erro: log (sem token) + aviso no Telegram + código 1
        detalhe = esconder_token("".join(traceback.format_exception(erro)), token)
        logger.error("A execução falhou:\n%s", detalhe)
        if token and chat_id:
            try:
                aviso = montar_aviso_falha(esconder_token(str(erro), token))
                enviar_texto(aviso, token, chat_id)
            except ErroTelegram as erro_aviso:
                logger.error("Nem o aviso de falha foi enviado: %s",
                             esconder_token(str(erro_aviso), token))
        return 1

    finally:
        # "finally" roda sempre, com ou sem erro
        logger.info(
            "Resumo: %d buscadas, %d aceitas pelo filtro, %d novas, %d enviadas, "
            "%d termos com falha",
            resumo["buscadas"], resumo["aceitas"], resumo["novas"],
            resumo["enviadas"], resumo["termos_com_falha"],
        )


def main(argv: list[str] | None = None) -> int:
    """Lê as opções da linha de comando, prepara tudo e chama executar()."""
    parser = argparse.ArgumentParser(description="Bot de vagas de estágio da Gupy")
    # As duas opções não fazem sentido juntas: o argparse impede usar as duas
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--dry-run", action="store_true",
                      help="mostra a mensagem no terminal, sem enviar e sem gravar no banco")
    modo.add_argument("--inicializar", action="store_true",
                      help="só registra as vagas atuais no banco, sem mensagem")
    parser.add_argument("--banco", type=Path, default=banco.CAMINHO_PADRAO,
                        help="caminho do banco SQLite (padrão: dados/vagas.db)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(FiltroSegredos())

    carregar_env()
    config = carregar_config()
    conn = banco.conectar(args.banco)
    try:
        return executar(config, conn, dry_run=args.dry_run, so_inicializar=args.inicializar)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())  # o código de saída diz ao GitHub Actions se deu certo
