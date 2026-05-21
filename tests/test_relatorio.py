"""
test_relatorio.py — Testes do relatório diário por e-mail (relatorio.py)
"""

from datetime import datetime
from unittest.mock import MagicMock, patch, call


# ===========================================================================
# _montar_html
# ===========================================================================
class TestMontarHtml:
    def _stats(self, d7=0, d1=0, cobranca=0, erros=0):
        return {
            "total": d7 + d1 + cobranca + erros,
            "enviados": d7 + d1 + cobranca,
            "erros": erros,
            "por_tipo": {
                **({"D-7": d7} if d7 else {}),
                **({"D-1": d1} if d1 else {}),
                **({"Cobranca": cobranca} if cobranca else {}),
            },
        }

    def test_html_contem_data_de_hoje(self):
        from relatorio import _montar_html
        html = _montar_html(self._stats(), [])
        hoje = datetime.now().strftime("%d/%m/%Y")
        assert hoje in html

    def test_html_sem_disparos_mostra_mensagem_vazia(self):
        from relatorio import _montar_html
        html = _montar_html(self._stats(), [])
        assert "Nenhum disparo hoje" in html

    def test_html_exibe_contadores(self):
        from relatorio import _montar_html
        html = _montar_html(self._stats(d7=3, d1=2, cobranca=1, erros=1), [])
        assert ">3<" in html  # D-7
        assert ">2<" in html  # D-1
        assert ">1<" in html  # Cobranca

    def test_html_com_disparo_mostra_cliente(self):
        from relatorio import _montar_html
        disparo = {
            "data_disparo": "20/05/2026 08:00:00",
            "nome": "Joao Silva",
            "vencimento": "25/05/2026",
            "tipo_disparo": "D-7",
            "status": "Enviado",
            "erro": "",
        }
        html = _montar_html(self._stats(d7=1), [disparo])
        assert "Joao Silva" in html
        assert "25/05/2026" in html

    def test_html_limita_50_linhas(self):
        from relatorio import _montar_html
        disparos = [
            {"data_disparo": "20/05/2026", "nome": f"Cliente{i}",
             "vencimento": "20/05/2026", "tipo_disparo": "D-1",
             "status": "Enviado", "erro": ""}
            for i in range(100)
        ]
        html = _montar_html(self._stats(d1=100), disparos)
        assert html.count("<tr>") <= 55  # 50 linhas + cabeçalho + tolerância

    def test_html_e_string_valida(self):
        from relatorio import _montar_html
        html = _montar_html(self._stats(), [])
        assert isinstance(html, str)
        assert "<html>" in html
        assert "</html>" in html


# ===========================================================================
# enviar_relatorio_diario
# ===========================================================================
class TestEnviarRelatorioDiario:
    def test_sem_config_retorna_false(self, monkeypatch):
        import relatorio
        monkeypatch.setattr(relatorio, "EMAIL_REMETENTE",    "")
        monkeypatch.setattr(relatorio, "EMAIL_SENHA",        "")
        monkeypatch.setattr(relatorio, "EMAIL_DESTINATARIO", "")
        assert relatorio.enviar_relatorio_diario() is False

    def test_smtp_ok_retorna_true(self, tmp_db, monkeypatch):
        import relatorio
        monkeypatch.setattr(relatorio, "EMAIL_REMETENTE",    "remetente@gmail.com")
        monkeypatch.setattr(relatorio, "EMAIL_SENHA",        "senha_app")
        monkeypatch.setattr(relatorio, "EMAIL_DESTINATARIO", "dest@empresa.com")
        monkeypatch.setattr(relatorio, "db", tmp_db)

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = lambda s: s
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("relatorio.smtplib.SMTP", return_value=mock_smtp):
            resultado = relatorio.enviar_relatorio_diario()

        assert resultado is True
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("remetente@gmail.com", "senha_app")
        mock_smtp.sendmail.assert_called_once()

    def test_smtp_falha_retorna_false(self, tmp_db, monkeypatch):
        import relatorio
        monkeypatch.setattr(relatorio, "EMAIL_REMETENTE",    "r@gmail.com")
        monkeypatch.setattr(relatorio, "EMAIL_SENHA",        "senha")
        monkeypatch.setattr(relatorio, "EMAIL_DESTINATARIO", "d@empresa.com")
        monkeypatch.setattr(relatorio, "db", tmp_db)

        with patch("relatorio.smtplib.SMTP", side_effect=Exception("connection refused")):
            resultado = relatorio.enviar_relatorio_diario()

        assert resultado is False

    def test_assunto_contem_data(self, tmp_db, monkeypatch):
        import relatorio
        monkeypatch.setattr(relatorio, "EMAIL_REMETENTE",    "r@gmail.com")
        monkeypatch.setattr(relatorio, "EMAIL_SENHA",        "senha")
        monkeypatch.setattr(relatorio, "EMAIL_DESTINATARIO", "d@empresa.com")
        monkeypatch.setattr(relatorio, "db", tmp_db)

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = lambda s: s
        mock_smtp.__exit__ = MagicMock(return_value=False)

        assunto_capturado = {}

        def fake_sendmail(from_, to_, msg_bytes):
            assunto_capturado["raw"] = msg_bytes.decode("utf-8", errors="replace")

        mock_smtp.sendmail = fake_sendmail

        with patch("relatorio.smtplib.SMTP", return_value=mock_smtp):
            relatorio.enviar_relatorio_diario()

        hoje = datetime.now().strftime("%d/%m/%Y")
        assert hoje in assunto_capturado.get("raw", "")
