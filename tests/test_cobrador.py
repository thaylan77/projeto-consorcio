"""
test_cobrador.py — Testes do módulo de cobrança D+2 (cobrador.py)
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


# ===========================================================================
# limpar_telefone (duplicada em cobrador.py — testamos a cópia local)
# ===========================================================================
class TestLimparTelefone:
    def setup_method(self):
        from cobrador import limpar_telefone
        self.fn = limpar_telefone

    def test_none_retorna_none(self):
        assert self.fn(None) is None

    def test_curto_retorna_none(self):
        assert self.fn("123") is None

    def test_adiciona_55(self):
        r = self.fn("11987654321")
        assert r.startswith("55")

    def test_adiciona_nono_digito(self):
        r = self.fn("551187654321")  # 12 dígitos
        assert len(r) == 13
        assert r[4] == "9"

    def test_remove_formatacao(self):
        r = self.fn("(11) 9.8765-4321")
        assert r == "5511987654321"


# ===========================================================================
# registrar_cobranca
# ===========================================================================
class TestRegistrarCobranca:
    def test_registra_como_cobranca(self, tmp_db, monkeypatch):
        import cobrador
        monkeypatch.setattr(cobrador, "db", tmp_db)

        cobrador.registrar_cobranca("Joao", "cpf123", "20/05/2026", "arq.pdf")
        r = tmp_db.listar_disparos()[0]
        assert r["tipo_disparo"] == "Cobranca"
        assert r["status"] == "Enviado"

    def test_registra_erro(self, tmp_db, monkeypatch):
        import cobrador
        monkeypatch.setattr(cobrador, "db", tmp_db)

        cobrador.registrar_cobranca("Ana", "cpf456", "20/05/2026", "arq.pdf",
                                     status="Erro", erro="Sem celular")
        r = tmp_db.listar_disparos()[0]
        assert r["status"] == "Erro"
        assert r["erro"] == "Sem celular"


# ===========================================================================
# encontrar_boletos_a_cobrar
# ===========================================================================
class TestEncontrarBoletosACobrar:
    def _venc(self, delta):
        return (datetime.now() + timedelta(days=delta)).strftime("%d/%m/%Y")

    def test_retorna_vencido(self, tmp_db, monkeypatch):
        import cobrador
        monkeypatch.setattr(cobrador, "db", tmp_db)

        tmp_db.registrar_disparo("X", "1", self._venc(-5), "b1.pdf",
                                   status="Enviado", tipo_disparo="D-1")
        resultado = cobrador.encontrar_boletos_a_cobrar()
        assert len(resultado) == 1

    def test_exclui_nao_vencido(self, tmp_db, monkeypatch):
        import cobrador
        monkeypatch.setattr(cobrador, "db", tmp_db)

        tmp_db.registrar_disparo("Y", "2", self._venc(1), "b2.pdf",
                                   status="Enviado", tipo_disparo="D-1")
        assert cobrador.encontrar_boletos_a_cobrar() == []

    def test_exclui_ja_cobrado(self, tmp_db, monkeypatch):
        import cobrador
        monkeypatch.setattr(cobrador, "db", tmp_db)

        tmp_db.registrar_disparo("Z", "3", self._venc(-5), "b3.pdf",
                                   status="Enviado", tipo_disparo="D-1")
        tmp_db.registrar_disparo("Z", "3", self._venc(-5), "b3.pdf",
                                   status="Enviado", tipo_disparo="Cobranca")
        assert cobrador.encontrar_boletos_a_cobrar() == []


# ===========================================================================
# enviar_cobranca
# ===========================================================================
class TestEnviarCobranca:
    def test_retorna_true_quando_200(self):
        from cobrador import enviar_cobranca
        resp = MagicMock()
        resp.status_code = 200
        with patch("cobrador.requests.post", return_value=resp):
            assert enviar_cobranca("5511999990001", "Maria", "20/05/2026") is True

    def test_retorna_true_quando_201(self):
        from cobrador import enviar_cobranca
        resp = MagicMock()
        resp.status_code = 201
        with patch("cobrador.requests.post", return_value=resp):
            assert enviar_cobranca("5511999990001", "Ana", "20/05/2026") is True

    def test_retorna_false_quando_400(self):
        from cobrador import enviar_cobranca
        resp = MagicMock()
        resp.status_code = 400
        resp.text = "Bad Request"
        with patch("cobrador.requests.post", return_value=resp):
            assert enviar_cobranca("5511999990001", "Pedro", "20/05/2026") is False

    def test_retorna_false_em_excecao(self):
        from cobrador import enviar_cobranca
        with patch("cobrador.requests.post", side_effect=ConnectionError("timeout")):
            assert enviar_cobranca("5511999990001", "Carlos", "20/05/2026") is False

    def test_mensagem_contem_nome_e_vencimento(self):
        from cobrador import enviar_cobranca
        resp = MagicMock()
        resp.status_code = 200
        with patch("cobrador.requests.post", return_value=resp) as mock_post:
            enviar_cobranca("5511999990001", "Fernanda", "31/12/2026")
            payload = mock_post.call_args[1]["json"]
            assert "Fernanda" in payload["message"]
            assert "31/12/2026" in payload["message"]


# ===========================================================================
# pula cliente que já informou pagamento via WhatsApp
# ===========================================================================
class TestPulaClientePago:
    def _venc(self, delta):
        return (datetime.now() + timedelta(days=delta)).strftime("%d/%m/%Y")

    def test_pula_se_telefone_pagou(self, tmp_db, monkeypatch):
        import cobrador
        monkeypatch.setattr(cobrador, "db", tmp_db)

        # Registra boleto vencido
        tmp_db.registrar_disparo("Paulo", "12345678901", self._venc(-5),
                                   "Boleto_12345678901_Venc-x.pdf",
                                   status="Enviado", tipo_disparo="D-1")

        # Simula que o cliente informou pagamento
        tmp_db.registrar_pagamento("5511999990001", "Paulo", "ja paguei")

        # CSV fake com o cliente
        csv_conteudo = "pessoacpfcnpj,celularformatado,pessoa\n12345678901,11999990001,Paulo\n"

        import io
        import pandas as pd

        mock_post = MagicMock()
        mock_post.return_value.status_code = 200

        with patch("cobrador.pd.read_csv", return_value=pd.read_csv(io.StringIO(csv_conteudo))):
            with patch("cobrador.requests.post", mock_post):
                with patch("cobrador.time.sleep"):
                    cobrador.executar_cobranca()

        # Não deve ter chamado requests.post pois o cliente já pagou
        mock_post.assert_not_called()
