"""Leitura do arquivo de configuração (config.toml) e do .env."""

import os
import tomllib
from pathlib import Path

# Caminho padrão: config.toml na raiz do projeto (uma pasta acima deste arquivo)
CAMINHO_PADRAO = Path(__file__).resolve().parent.parent / "config.toml"
# Segredos locais (no GitHub Actions eles vêm dos Secrets, sem arquivo .env)
CAMINHO_ENV = Path(__file__).resolve().parent.parent / ".env"


def carregar_config(caminho: str | Path = CAMINHO_PADRAO) -> dict:
    """Lê o arquivo TOML e devolve um dicionário com as configurações."""
    # O tomllib exige que o arquivo seja aberto em modo binário ("rb")
    with open(caminho, "rb") as arquivo:
        return tomllib.load(arquivo)


def carregar_env(caminho: str | Path = CAMINHO_ENV) -> None:
    """Lê o .env como TEXTO e coloca os valores nas variáveis de ambiente.

    Nunca executa o arquivo (como o `source` do terminal faria) e nunca
    imprime valores. Espaços em volta do "=" são ignorados. Variáveis que
    já existem não são sobrescritas (no Actions elas vêm dos Secrets).
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return  # sem .env: normal no GitHub Actions

    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue  # linha vazia, comentário ou sem "="
        linha = linha.removeprefix("export ")  # aceita "export NOME=valor"
        nome, valor = linha.split("=", 1)  # corta só no PRIMEIRO "="
        nome = nome.strip()
        valor = valor.strip().strip('"').strip("'")  # tira espaços e aspas
        if nome and nome not in os.environ:
            os.environ[nome] = valor
