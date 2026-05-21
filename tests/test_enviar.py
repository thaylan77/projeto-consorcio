"""
test_enviar.py — Testes das funções puras e lógica de envio (enviar.py)
"""

import os
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest


# ===========================================================================
# limpar_telefone
# ===========================================================================
class TestLimparTelefone:
    def setup_method(self):
        # Importa apenas a função pura, sem efeito colateral de rede
        from enviar import limpar_telefone
        self.fn = limpar_telefone

    def test_none_retorna_none(self):
        assert self.fn(None) is None

    def test_vazio_retorna_none(self):
        assert self.fn("") is None

    def test_muito_curto_retorna_none(self):
        assert self.fn("1234") is None

    def test_adiciona_prefixo_brasil(self):
        # (11) 98765-4321 → 5511987654321
        assert self.fn("11987654321") == "5511987654321"

    def test_adiciona_nono_digito(self):
        # 12 dígitos (55 + DDD + 8): adiciona 9
        assert self.fn("5511987654321") == "5511987654321"

    def test_remove_caracteres_nao_numericos(self):
        assert self.fn("(11) 9 8765-4321") == "5511987654321"

    def test_ja_tem_55_e_13_digitos(self):
        resultado = self.fn("5511987654321")
        assert resultado.startswith("55")
        assert len(resultado) == 13

    def test_adiciona_9_quando_12_digitos(self):
        # 55 + DDD (2) + numero (8) = 12 → insere 9 após DDD
        resultado = self.fn("551187654321")
        assert len(resultado) == 13
        assert resultado[4] == "9"


# ===========================================================================
# classificar_envio
# ===========================================================================
class TestClassificarEnvio:
    def setup_method(self):
        from enviar import classificar_envio
        self.fn = classificar_envio

    def test_d7_no_centro_da_janela(self):
        assert self.fn(7) == "D-7"

    def test_d7_na_borda_minima(self):
        assert self.fn(5) == "D-7"

    def test_d7_na_borda_maxima(self):
        assert self.fn(9) == "D-7"

    def test_d1_no_dia(self):
        assert self.fn(0) == "D-1"

    def test_d1_amanha(self):
        assert self.fn(1) == "D-1"

    def test_d1_borda_maxima(self):
        assert self.fn(4) == "D-1"

    def test_fora_da_janela_futuro(self):
        assert self.fn(15) is None

    def test_vencido_negativo(self):
        assert self.fn(-3) is None


# ===========================================================================
# _montar_mensagem
# ===========================================================================
class TestMontarMensagem:
    def setup_method(self):
        from enviar import _montar_mensagem
        self.fn = _montar_mensagem

    def test_d7_contem_data_vencimento(self):
        msg = self.fn("Joao", "30/05/2026", "D-7")
        assert "30/05/2026" in msg
        assert "Joao" in msg

    def test_d7_menciona_antecipado(self):
        msg = self.fn("Ana", "30/05/2026", "D-7")
        assert "vence em" in msg.lower()

    def test_d1_menciona_amanha(self):
        msg = self.fn("Pedro", "30/05/2026", "D-1")
        assert "amanha" in msg.lower()

    def test_d1_contem_data(self):
        msg = self.fn("Maria", "30/05/2026", "D-1")
        assert "30/05/2026" in msg

    def test_assinatura_presente(self):
        for tipo in ("D-7", "D-1"):
            msg = self.fn("X", "01/01/2026", tipo)
            assert "Socel Motos" in msg


# ===========================================================================
# registrar_historico (mascara CPF e delega ao db)
# ===========================================================================
class TestRegistrarHistorico:
    def test_mascara_cpf_11_digitos(self, tmp_db, monkeypatch):
        import enviar
        monkeypatch.setattr(enviar, "db", tmp_db)

        enviar.registrar_historico("joao silva", "12345678901", "20/05/2026", "arq.pdf")
        r = tmp_db.listar_disparos()[0]
        assert "123" in r["cpf"]
        assert "01" in r["cpf"]
        # dígitos do meio mascarados
        assert "456789" not in r["cpf"]

    def test_capitaliza_nome(self, tmp_db, monkeypatch):
        import enviar
        monkeypatch.setattr(enviar, "db", tmp_db)

        enviar.registrar_historico("joao da silva", "12345678901", "20/05/2026", "arq.pdf")
        r = tmp_db.listar_disparos()[0]
        assert r["nome"] == "Joao Da Silva"

    def test_nome_vazio_usa_desconhecido(self, tmp_db, monkeypatch):
        import enviar
        monkeypatch.setattr(enviar, "db", tmp_db)

        enviar.registrar_historico("", "123", "20/05/2026", "arq.pdf")
        r = tmp_db.listar_disparos()[0]
        assert r["nome"] == "Desconhecido"


# ===========================================================================
# enviar_whatsapp (mocks de rede)
# ===========================================================================
class TestEnviarWhatsapp:
    def _dados_cliente(self):
        return {"nome": "Maria Souza", "telefone": "5511999990001"}

    def test_sucesso_texto_e_pdf(self, tmp_db, monkeypatch, tmp_path):
        import enviar
        monkeypatch.setattr(enviar, "db", tmp_db)

        # Cria PDF temporário
        pdf = tmp_path / "Boleto_11111111111_Venc-20-05-2026.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        resp_ok = MagicMock()
        resp_ok.status_code = 200

        with patch("enviar.requests.post", return_value=resp_ok):
            with patch("enviar.time.sleep"):
                resultado = enviar.enviar_whatsapp(
                    self._dados_cliente(), str(pdf), "20/05/2026", "D-1"
                )

        assert resultado is True
        # Deve ter registrado no banco como Enviado
        r = tmp_db.listar_disparos()[0]
        assert r["status"] == "Enviado"
        assert r["tipo_disparo"] == "D-1"

    def test_erro_no_envio_de_texto(self, tmp_db, monkeypatch, tmp_path):
        import enviar
        monkeypatch.setattr(enviar, "db", tmp_db)

        pdf = tmp_path / "Boleto_22222222222_Venc-20-05-2026.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        resp_erro = MagicMock()
        resp_erro.status_code = 500
        resp_erro.text = "Internal Server Error"

        with patch("enviar.requests.post", return_value=resp_erro):
            with patch("enviar.time.sleep"):
                resultado = enviar.enviar_whatsapp(
                    self._dados_cliente(), str(pdf), "20/05/2026", "D-7"
                )

        assert resultado is False
        r = tmp_db.listar_disparos()[0]
        assert r["status"] == "Erro"

    def test_excecao_de_conexao(self, tmp_db, monkeypatch, tmp_path):
        import enviar
        monkeypatch.setattr(enviar, "db", tmp_db)

        pdf = tmp_path / "Boleto_33333333333_Venc-20-05-2026.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        with patch("enviar.requests.post", side_effect=ConnectionError("timeout")):
            with patch("enviar.time.sleep"):
                resultado = enviar.enviar_whatsapp(
                    self._dados_cliente(), str(pdf), "20/05/2026", "D-1"
                )

        assert resultado is False

    def test_retry_pdf_sucesso_na_segunda_tentativa(self, tmp_db, monkeypatch, tmp_path):
        import enviar
        monkeypatch.setattr(enviar, "db", tmp_db)

        pdf = tmp_path / "Boleto_44444444444_Venc-20-05-2026.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        resp_ok = MagicMock(); resp_ok.status_code = 200
        resp_erro = MagicMock(); resp_erro.status_code = 500; resp_erro.text = "erro"

        # 1ª chamada = texto (ok), 2ª = PDF falha, 3ª = PDF sucesso
        with patch("enviar.requests.post",
                   side_effect=[resp_ok, resp_erro, resp_ok]):
            with patch("enviar.time.sleep"):
                resultado = enviar.enviar_whatsapp(
                    self._dados_cliente(), str(pdf), "20/05/2026", "D-1"
                )

        assert resultado is True

    def test_retry_pdf_falha_todas_tentativas(self, tmp_db, monkeypatch, tmp_path):
        import enviar
        monkeypatch.setattr(enviar, "db", tmp_db)

        pdf = tmp_path / "Boleto_55555555555_Venc-20-05-2026.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        resp_ok = MagicMock(); resp_ok.status_code = 200
        resp_erro = MagicMock(); resp_erro.status_code = 500; resp_erro.text = "erro"

        # texto ok, mas PDF falha nas 3 tentativas
        with patch("enviar.requests.post",
                   side_effect=[resp_ok, resp_erro, resp_erro, resp_erro]):
            with patch("enviar.time.sleep"):
                resultado = enviar.enviar_whatsapp(
                    self._dados_cliente(), str(pdf), "20/05/2026", "D-1"
                )

        assert resultado is False
        r = tmp_db.listar_disparos()[0]
        assert r["status"] == "Erro"
