import os
import sys
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        print(f"[ERRO] Variavel obrigatoria nao configurada: {key}")
        print(f"       Edite o arquivo .env na raiz do projeto.")
        sys.exit(1)
    return val


# Credenciais
BEARER_TOKEN   = _require("BEARER_TOKEN_MICROWORK")
TOKEN_SUNCHAT  = _require("TOKEN_SUNCHAT")
CNY_USUARIO    = _require("CNY_USUARIO")
CNY_SENHA      = _require("CNY_SENHA")
API_SECRET_KEY = _require("API_SECRET_KEY")

# Diretório raiz do projeto (independente do CWD)
_PROJ_DIR = os.path.dirname(os.path.abspath(__file__))

# Paths
PASTA_BASE           = os.getenv("PASTA_BASE", r"C:\Boletos")
PASTA_PARA_ENVIAR    = os.getenv("PASTA_PARA_ENVIAR",    os.path.join(PASTA_BASE, "Para_Enviar"))
PASTA_VALIDADOS      = os.getenv("PASTA_VALIDADOS",      os.path.join(PASTA_BASE, "Validados"))
PASTA_REJEITADOS     = os.getenv("PASTA_REJEITADOS",     os.path.join(PASTA_BASE, "Rejeitados"))
PASTA_ENVIADOS       = os.getenv("PASTA_ENVIADOS",       os.path.join(PASTA_BASE, "Enviados"))
PASTA_REVISAO_MANUAL = os.getenv("PASTA_REVISAO_MANUAL", os.path.join(PASTA_BASE, "Revisao_Manual"))
ARQUIVO_HISTORICO    = os.getenv("ARQUIVO_HISTORICO",    os.path.join(PASTA_BASE, "historico_envios.json"))

# Log — caminho absoluto para garantir que app.log sempre vai para a pasta do projeto
LOG_FILE         = os.getenv("LOG_FILE", os.path.join(_PROJ_DIR, "app.log"))
LOG_MAX_MB       = int(os.getenv("LOG_MAX_MB", "10"))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))

# Regras de negócio
VALOR_MINIMO_EMISSAO = float(os.getenv("VALOR_MINIMO_EMISSAO", "15.00"))
MESES_RETROATIVOS    = int(os.getenv("MESES_RETROATIVOS", "9"))

# Janelas de envio automático
# D-7: envia aviso antecipado quando faltam entre JANELA_D7_MIN e JANELA_D7_MAX dias
JANELA_D7_MIN = int(os.getenv("JANELA_D7_MIN", "5"))
JANELA_D7_MAX = int(os.getenv("JANELA_D7_MAX", "9"))

# D-1: envia lembrete final quando faltam entre JANELA_D1_MIN e JANELA_D1_MAX dias
JANELA_D1_MIN = int(os.getenv("JANELA_D1_MIN", "0"))
JANELA_D1_MAX = int(os.getenv("JANELA_D1_MAX", "4"))

# Cobrança D+2: dias após o vencimento para disparar a mensagem de cobrança
DIAS_APOS_VENC_PARA_COBRAR = int(os.getenv("DIAS_APOS_VENC_PARA_COBRAR", "2"))

# Agendador
HORA_PIPELINE  = os.getenv("HORA_PIPELINE", "08:00")
HORA_COBRADOR  = os.getenv("HORA_COBRADOR", "09:00")
HORA_RESPOSTAS = os.getenv("HORA_RESPOSTAS", "10:00")

# IA (Anthropic Claude) — opcional, deixe vazio para desabilitar
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL   = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# Webhook Sunchat — segredo compartilhado para autenticar POSTs recebidos
# Se vazio, o webhook aceita qualquer requisição (retrocompatível, mas não recomendado)
SUNCHAT_WEBHOOK_SECRET = os.getenv("SUNCHAT_WEBHOOK_SECRET", "")

# Banco de dados SQLite
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "consorcio.db"))

# Relatório diário por e-mail — opcional, deixe vazio para desabilitar
EMAIL_REMETENTE    = os.getenv("EMAIL_REMETENTE", "")
EMAIL_SENHA        = os.getenv("EMAIL_SENHA", "")
EMAIL_DESTINATARIO = os.getenv("EMAIL_DESTINATARIO", "")
SMTP_HOST          = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT          = int(os.getenv("SMTP_PORT", "587"))
