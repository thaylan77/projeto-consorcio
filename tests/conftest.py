"""
conftest.py — Configuração global de testes

Define variáveis de ambiente antes de qualquer importação do projeto,
e fornece fixtures compartilhadas entre todos os módulos de teste.
"""

import os
import sys
import tempfile

# Garante que o diretório raiz do projeto esteja no sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Define vars obrigatórias ANTES de qualquer import do projeto
os.environ.setdefault("BEARER_TOKEN_MICROWORK", "tok_test_bearer")
os.environ.setdefault("TOKEN_SUNCHAT",          "tok_test_sunchat")
os.environ.setdefault("CNY_USUARIO",            "usuario_teste")
os.environ.setdefault("CNY_SENHA",              "senha_teste")
os.environ.setdefault("API_SECRET_KEY",         "sk_test_key_12345")
os.environ.setdefault("PASTA_BASE",             tempfile.mkdtemp())
os.environ.setdefault("ANTHROPIC_API_KEY",      "")
os.environ.setdefault("EMAIL_REMETENTE",        "")
os.environ.setdefault("EMAIL_SENHA",            "")
os.environ.setdefault("EMAIL_DESTINATARIO",     "")

import pytest


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Banco SQLite temporário — isolado por teste."""
    import db
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "DB_PATH", db_file)
    db.init_db()
    yield db
    # tmp_path é limpo automaticamente pelo pytest
