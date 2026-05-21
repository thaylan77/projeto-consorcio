"""
relatorio.py — Relatório diário por e-mail

Envia um e-mail com resumo do dia: disparos D-7, D-1, cobranças e erros.
Configuração via .env:
  EMAIL_REMETENTE, EMAIL_SENHA, EMAIL_DESTINATARIO
  SMTP_HOST (padrão smtp.gmail.com), SMTP_PORT (padrão 587)
"""

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import db
from logger import log

MODULO = "Relatorio"

EMAIL_REMETENTE    = os.getenv("EMAIL_REMETENTE", "")
EMAIL_SENHA        = os.getenv("EMAIL_SENHA", "")
EMAIL_DESTINATARIO = os.getenv("EMAIL_DESTINATARIO", "")
SMTP_HOST          = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT          = int(os.getenv("SMTP_PORT", "587"))


def _montar_html(stats: dict, disparos: list) -> str:
    hoje = datetime.now().strftime("%d/%m/%Y")
    por_tipo = stats.get("por_tipo", {})

    linhas_tabela = ""
    for d in disparos[:50]:  # limita a 50 linhas no e-mail
        cor_status = "#27ae60" if d.get("status") == "Enviado" else "#e74c3c"
        cor_tipo   = {
            "D-7":      "#2980b9",
            "D-1":      "#f39c12",
            "Cobranca": "#e74c3c",
        }.get(d.get("tipo_disparo", ""), "#7f8c8d")
        linhas_tabela += (
            f"<tr>"
            f"<td>{d.get('data_disparo','')}</td>"
            f"<td>{d.get('nome','')}</td>"
            f"<td>{d.get('vencimento','')}</td>"
            f"<td style='color:{cor_tipo};font-weight:bold'>{d.get('tipo_disparo','')}</td>"
            f"<td style='color:{cor_status};font-weight:bold'>{d.get('status','')}</td>"
            f"<td style='font-size:11px;color:#555'>{d.get('erro','')}</td>"
            f"</tr>\n"
        )

    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; color: #333; }}
    h2   {{ color: #2c3e50; }}
    .card {{ display:inline-block; margin:8px; padding:16px 24px;
             border-radius:8px; text-align:center; color:#fff; min-width:100px; }}
    .verde   {{ background:#27ae60; }}
    .azul    {{ background:#2980b9; }}
    .amarelo {{ background:#f39c12; }}
    .vermelho{{ background:#e74c3c; }}
    .cinza   {{ background:#7f8c8d; }}
    table {{ border-collapse:collapse; width:100%; margin-top:16px; font-size:13px; }}
    th,td {{ border:1px solid #ddd; padding:7px 10px; text-align:left; }}
    th {{ background:#2c3e50; color:#fff; }}
    tr:nth-child(even) {{ background:#f9f9f9; }}
  </style>
</head>
<body>
  <h2>Relatorio do Consorcio — {hoje}</h2>

  <div>
    <div class="card azul">
      <div style="font-size:28px;font-weight:bold">{por_tipo.get('D-7', 0)}</div>
      <div>D-7 enviados</div>
    </div>
    <div class="card amarelo">
      <div style="font-size:28px;font-weight:bold">{por_tipo.get('D-1', 0)}</div>
      <div>D-1 enviados</div>
    </div>
    <div class="card vermelho">
      <div style="font-size:28px;font-weight:bold">{por_tipo.get('Cobranca', 0)}</div>
      <div>Cobranças</div>
    </div>
    <div class="card {"vermelho" if stats.get("erros",0) > 0 else "verde"}">
      <div style="font-size:28px;font-weight:bold">{stats.get("erros", 0)}</div>
      <div>Erros</div>
    </div>
    <div class="card cinza">
      <div style="font-size:28px;font-weight:bold">{stats.get("total", 0)}</div>
      <div>Total disparos</div>
    </div>
  </div>

  <h3>Detalhes dos disparos de hoje</h3>
  <table>
    <thead>
      <tr>
        <th>Data/Hora</th><th>Cliente</th><th>Vencimento</th>
        <th>Tipo</th><th>Status</th><th>Erro</th>
      </tr>
    </thead>
    <tbody>
      {linhas_tabela if linhas_tabela else '<tr><td colspan="6" style="text-align:center;color:#999">Nenhum disparo hoje</td></tr>'}
    </tbody>
  </table>

  <p style="margin-top:24px;font-size:11px;color:#999">
    Gerado automaticamente pelo sistema de consorcio — Socel Motos / Terrasal Automoveis
  </p>
</body>
</html>
"""


def enviar_relatorio_diario() -> bool:
    if not all([EMAIL_REMETENTE, EMAIL_SENHA, EMAIL_DESTINATARIO]):
        log("E-mail nao configurado (EMAIL_REMETENTE/EMAIL_SENHA/EMAIL_DESTINATARIO). Relatorio ignorado.",
            "WARNING", MODULO)
        return False

    hoje = datetime.now().strftime("%d/%m/%Y")
    stats = db.stats_do_dia()
    disparos_hoje = [
        d for d in db.listar_disparos(500)
        if d.get("data_disparo", "").startswith(hoje)
    ]

    html = _montar_html(stats, disparos_hoje)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Relatorio Consorcio {hoje} | D-7:{stats['por_tipo'].get('D-7',0)} D-1:{stats['por_tipo'].get('D-1',0)} Cobr:{stats['por_tipo'].get('Cobranca',0)} Erros:{stats['erros']}"
    msg["From"]    = EMAIL_REMETENTE
    msg["To"]      = EMAIL_DESTINATARIO
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(EMAIL_REMETENTE, EMAIL_SENHA)
            srv.sendmail(EMAIL_REMETENTE, EMAIL_DESTINATARIO, msg.as_bytes())
        log(f"Relatorio diario enviado para {EMAIL_DESTINATARIO}.", "SUCCESS", MODULO)
        return True
    except Exception as e:
        log(f"Falha ao enviar relatorio por e-mail: {e}", "ERROR", MODULO)
        return False


if __name__ == "__main__":
    enviar_relatorio_diario()
