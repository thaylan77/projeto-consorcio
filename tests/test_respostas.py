"""
test_respostas.py — Testes do processador de respostas WhatsApp com IA (respostas_whatsapp.py)
"""

from unittest.mock import MagicMock, patch


# ===========================================================================
# classificar_intencao
# ===========================================================================
class TestClassificarIntencao:
    def test_sem_api_key_retorna_outro(self, monkeypatch):
        import respostas_whatsapp as rw
        monkeypatch.setattr(rw, "ANTHROPIC_API_KEY", "")
        resultado = rw.classificar_intencao("oi", "Joao")
        assert resultado == "OUTRO"

    def test_ja_pagou(self, monkeypatch):
        import respostas_whatsapp as rw
        monkeypatch.setattr(rw, "ANTHROPIC_API_KEY", "sk_fake")
        mock_client = MagicMock()
        mock_client.messages.create.return_value.content = [MagicMock(text="JA_PAGOU")]
        with patch("respostas_whatsapp.anthropic.Anthropic", return_value=mock_client):
            assert rw.classificar_intencao("Ja paguei!", "Maria") == "JA_PAGOU"

    def test_pedir_boleto(self, monkeypatch):
        import respostas_whatsapp as rw
        monkeypatch.setattr(rw, "ANTHROPIC_API_KEY", "sk_fake")
        mock_client = MagicMock()
        mock_client.messages.create.return_value.content = [MagicMock(text="PEDIR_BOLETO")]
        with patch("respostas_whatsapp.anthropic.Anthropic", return_value=mock_client):
            assert rw.classificar_intencao("manda o boleto de novo", "Pedro") == "PEDIR_BOLETO"

    def test_categoria_invalida_fallback_outro(self, monkeypatch):
        """Resposta inesperada da IA deve retornar OUTRO."""
        import respostas_whatsapp as rw
        monkeypatch.setattr(rw, "ANTHROPIC_API_KEY", "sk_fake")
        mock_client = MagicMock()
        mock_client.messages.create.return_value.content = [MagicMock(text="CATEGORIA_ESTRANHA")]
        with patch("respostas_whatsapp.anthropic.Anthropic", return_value=mock_client):
            assert rw.classificar_intencao("...", "X") == "OUTRO"

    def test_excecao_da_api_retorna_outro(self, monkeypatch):
        """Erro na API Claude não deve propagar — retorna OUTRO."""
        import respostas_whatsapp as rw
        monkeypatch.setattr(rw, "ANTHROPIC_API_KEY", "sk_fake")
        with patch("respostas_whatsapp.anthropic.Anthropic",
                   side_effect=Exception("API unavailable")):
            assert rw.classificar_intencao("teste", "Ana") == "OUTRO"

    def test_uppercase_normalizado(self, monkeypatch):
        """Resposta com espaços extras deve ser normalizada."""
        import respostas_whatsapp as rw
        monkeypatch.setattr(rw, "ANTHROPIC_API_KEY", "sk_fake")
        mock_client = MagicMock()
        mock_client.messages.create.return_value.content = [MagicMock(text="  ja_pagou  ")]
        with patch("respostas_whatsapp.anthropic.Anthropic", return_value=mock_client):
            assert rw.classificar_intencao("paguei", "Z") == "JA_PAGOU"


# ===========================================================================
# marcar_como_pago / telefone_ja_pagou (delegam ao db)
# ===========================================================================
class TestPagamentos:
    def test_marcar_e_verificar(self, tmp_db, monkeypatch):
        import respostas_whatsapp as rw
        monkeypatch.setattr(rw, "db", tmp_db)
        rw.marcar_como_pago("5511999990001", "Joao", "ja paguei")
        assert rw.telefone_ja_pagou("5511999990001") is True

    def test_nao_cadastrado_retorna_false(self, tmp_db, monkeypatch):
        import respostas_whatsapp as rw
        monkeypatch.setattr(rw, "db", tmp_db)
        assert rw.telefone_ja_pagou("5500000000000") is False


# ===========================================================================
# processar_resposta — fluxo completo
# ===========================================================================
class TestProcessarResposta:
    def _setup(self, monkeypatch, tmp_db, intencao: str):
        import respostas_whatsapp as rw
        monkeypatch.setattr(rw, "db", tmp_db)
        monkeypatch.setattr(rw, "classificar_intencao",
                            lambda msg, nome: intencao)
        monkeypatch.setattr(rw, "_carregar_mapa_clientes",
                            lambda: {"5511999990001": {"nome": "Maria Silva", "cpf": "12345678901"}})
        return rw

    def test_ja_pagou_marca_e_responde(self, tmp_db, monkeypatch):
        rw = self._setup(monkeypatch, tmp_db, "JA_PAGOU")
        with patch("respostas_whatsapp._enviar_texto", return_value=True):
            resultado = rw.processar_resposta("5511999990001", "ja paguei")
        assert resultado["intencao"] == "JA_PAGOU"
        assert resultado["acao"] == "pagamento_marcado"
        assert resultado["sucesso"] is True
        assert tmp_db.telefone_ja_pagou("5511999990001") is True

    def test_pedir_boleto_reenviado(self, tmp_db, monkeypatch):
        rw = self._setup(monkeypatch, tmp_db, "PEDIR_BOLETO")
        with patch("respostas_whatsapp._reenviar_boleto", return_value=True):
            with patch("respostas_whatsapp._enviar_texto", return_value=True):
                resultado = rw.processar_resposta("5511999990001", "manda o boleto")
        assert resultado["acao"] == "boleto_reenviado"
        assert resultado["sucesso"] is True

    def test_pedir_boleto_nao_encontrado(self, tmp_db, monkeypatch):
        rw = self._setup(monkeypatch, tmp_db, "PEDIR_BOLETO")
        with patch("respostas_whatsapp._reenviar_boleto", return_value=False):
            resultado = rw.processar_resposta("5511999990001", "manda o boleto")
        assert resultado["acao"] == "boleto_nao_encontrado"
        assert resultado["sucesso"] is False

    def test_pedir_prazo_encaminha_humano(self, tmp_db, monkeypatch):
        rw = self._setup(monkeypatch, tmp_db, "PEDIR_PRAZO")
        with patch("respostas_whatsapp._enviar_texto", return_value=True):
            resultado = rw.processar_resposta("5511999990001", "preciso de prazo")
        assert resultado["acao"] == "encaminhado_humano"

    def test_reclamacao_encaminha_humano(self, tmp_db, monkeypatch):
        rw = self._setup(monkeypatch, tmp_db, "RECLAMACAO")
        with patch("respostas_whatsapp._enviar_texto", return_value=True):
            resultado = rw.processar_resposta("5511999990001", "que absurdo isso")
        assert resultado["acao"] == "encaminhado_humano"

    def test_outro_ignora(self, tmp_db, monkeypatch):
        rw = self._setup(monkeypatch, tmp_db, "OUTRO")
        resultado = rw.processar_resposta("5511999990001", "ok")
        assert resultado["acao"] == "ignorado"

    def test_telefone_desconhecido_usa_cliente_padrao(self, tmp_db, monkeypatch):
        import respostas_whatsapp as rw
        monkeypatch.setattr(rw, "db", tmp_db)
        monkeypatch.setattr(rw, "classificar_intencao", lambda m, n: "OUTRO")
        monkeypatch.setattr(rw, "_carregar_mapa_clientes", lambda: {})
        resultado = rw.processar_resposta("5500000000000", "oi")
        assert resultado["nome"] == "Cliente"
        assert resultado["acao"] == "ignorado"
