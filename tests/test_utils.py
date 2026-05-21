"""
test_utils.py — Testes das funções utilitárias compartilhadas (utils.py)
"""

import pytest
from utils import limpar_telefone, normalizar


class TestLimparTelefone:
    def test_none_retorna_none(self):
        assert limpar_telefone(None) is None

    def test_vazio_retorna_none(self):
        assert limpar_telefone("") is None

    def test_muito_curto_retorna_none(self):
        assert limpar_telefone("1234567") is None

    def test_adiciona_prefixo_55(self):
        assert limpar_telefone("11987654321") == "5511987654321"

    def test_remove_formatacao(self):
        assert limpar_telefone("(11) 9.8765-4321") == "5511987654321"

    def test_nao_duplica_55(self):
        resultado = limpar_telefone("5511987654321")
        assert resultado.startswith("55")
        assert not resultado.startswith("5555")

    def test_insere_nono_digito_em_12_chars(self):
        # 55 + DDD(2) + 8 dígitos = 12 → deve virar 13
        resultado = limpar_telefone("551187654321")
        assert len(resultado) == 13
        assert resultado[4] == "9"

    def test_13_digitos_nao_altera(self):
        resultado = limpar_telefone("5511987654321")
        assert len(resultado) == 13

    def test_numero_internacional_sem_55(self):
        # número de 10 dígitos sem DDD 55
        resultado = limpar_telefone("11987654321")
        assert resultado.startswith("55")

    def test_aceita_int_como_entrada(self):
        resultado = limpar_telefone(11987654321)
        assert resultado is not None
        assert resultado.startswith("55")


class TestNormalizar:
    def test_remove_acentos(self):
        assert normalizar("José") == "JOSE"

    def test_converte_para_maiusculo(self):
        assert normalizar("joao") == "JOAO"

    def test_remove_cedilha(self):
        assert normalizar("coração") == "coracao".upper()

    def test_remove_quebra_de_linha(self):
        assert "\n" not in normalizar("linha1\nlinha2")

    def test_strip_espacos(self):
        assert normalizar("  texto  ") == "TEXTO"

    def test_entrada_nao_string_retorna_vazio(self):
        assert normalizar(None) == ""
        assert normalizar(123) == ""

    def test_string_vazia(self):
        assert normalizar("") == ""

    def test_multiplos_acentos(self):
        resultado = normalizar("ção ãe íü")
        assert "ç" not in resultado
        assert "ã" not in resultado
        assert "í" not in resultado
        assert "ü" not in resultado
