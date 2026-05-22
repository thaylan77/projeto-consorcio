"""
cny_client.py — Cliente Selenium reutilizável para o portal CNY

Funções públicas:
  iniciar_sessao()                              → (driver, wait) | (None, None)
  encerrar_sessao(driver)
  verificar_boleto_pago(driver, wait, cpf, vencimento) → bool
"""

import re
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, WebDriverException,
)

from config import CNY_USUARIO, CNY_SENHA, PASTA_PARA_ENVIAR
from logger import log

MODULO = "CNY-Client"
_URL_BASE = "https://newkey.cny.com.br/Intranet/"

# Situações que indicam contrato/boleto quitado
_STATUS_PAGO = {"QUI", "QUITADO", "LIQ", "LIQUIDADO"}

# Situações descartadas (cancelado, suspenso…) — não cobrar mas também não é "pago"
_STATUS_IGNORAR = {"CAN", "CANCELADO", "EXCLUIDO", "CA2", "TRA", "SUS"}


# =============================================================================
# OPÇÕES DO CHROME
# =============================================================================
def _criar_options() -> webdriver.ChromeOptions:
    opts = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": PASTA_PARA_ENVIAR,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    }
    opts.add_experimental_option("prefs", prefs)
    opts.add_argument("--log-level=3")
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    return opts


# =============================================================================
# SESSÃO
# =============================================================================
def iniciar_sessao():
    """
    Abre o Chrome, faz login e navega até a tela de emissão de boletos.
    Retorna (driver, wait) em caso de sucesso ou (None, None) em falha.
    """
    log("Iniciando sessao CNY...", modulo=MODULO)
    try:
        driver = webdriver.Chrome(options=_criar_options())
        wait = WebDriverWait(driver, 30)

        driver.get(_URL_BASE)
        wait.until(EC.presence_of_element_located((By.ID, "edtUsuario"))).send_keys(CNY_USUARIO)
        wait.until(EC.presence_of_element_located((By.ID, "edtSenha"))).send_keys(CNY_SENHA)
        wait.until(EC.element_to_be_clickable((By.ID, "btnLogin"))).click()

        wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="CO"]'))).click()
        wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="subs"]/ul/li[2]/a'))).click()
        wait.until(EC.element_to_be_clickable((By.ID, "ctl00_Conteudo_ctl00_tvwMenut2"))).click()

        log("Sessao CNY iniciada.", modulo=MODULO)
        return driver, wait
    except Exception as e:
        log(f"Falha ao iniciar sessao CNY: {e}", "ERROR", MODULO)
        try:
            driver.quit()
        except Exception:
            pass
        return None, None


def encerrar_sessao(driver) -> None:
    try:
        driver.quit()
        log("Sessao CNY encerrada.", modulo=MODULO)
    except Exception:
        pass


# =============================================================================
# VERIFICAÇÃO DE PAGAMENTO
# =============================================================================
def verificar_boleto_pago(driver, wait, cpf: str, vencimento: str) -> bool:
    """
    Consulta o portal CNY e retorna True se o boleto com o vencimento
    informado já foi liquidado para este CPF.

    Estratégia:
      1. Busca o cliente por CPF.
      2. Se o status do contrato for QUI/QUITADO/LIQ → pago.
      3. Navega até a tabela de boletos e procura a linha com o vencimento.
      4. Se a linha não possui checkbox de emissão (boleto já emitido/quitado) → pago.
      5. Se não consegue determinar → retorna False (cobra para não deixar passar).
    """
    cpf = re.sub(r"\D", "", cpf)
    log(f"Verificando pagamento CNY: CPF {cpf[:3]}***{cpf[-2:]} venc {vencimento}", modulo=MODULO)

    try:
        # ── Reset de tela ──────────────────────────────────────────────────────
        try:
            driver.find_element(By.ID, "ctl00_Conteudo_ctl00_tvwMenut2").click()
        except NoSuchElementException:
            try:
                wait.until(EC.element_to_be_clickable(
                    (By.XPATH, '//*[@id="subs"]/ul/li[2]/a'))).click()
                wait.until(EC.element_to_be_clickable(
                    (By.ID, "ctl00_Conteudo_ctl00_tvwMenut2"))).click()
            except Exception:
                pass

        wait.until(EC.element_to_be_clickable(
            (By.ID, "ctl00_Conteudo_identificacao_cota_btnBuscaAvancada")
        )).click()

        # ── Selecionar busca por CPF ───────────────────────────────────────────
        wait.until(EC.presence_of_element_located(
            (By.ID, "ctl00_Conteudo_cbxCriterioBusca")))
        driver.execute_script(
            "var d=document.getElementById('ctl00_Conteudo_cbxCriterioBusca');"
            "d.value='F';"
            "__doPostBack('ctl00$Conteudo$cbxCriterioBusca','');"
        )
        campo = wait.until(EC.element_to_be_clickable(
            (By.ID, "ctl00_Conteudo_edtContextoBusca")))
        campo.clear()
        campo.send_keys(cpf)
        driver.find_element(By.ID, "ctl00_Conteudo_btnBuscar").click()

        wait.until(lambda d: (
            d.find_elements(By.ID, "ctl00_Conteudo_grdBuscaAvancada_ctl02_lnkCD_Situacao_Cobranca")
            or d.find_elements(By.ID, "ctl00_Conteudo_lblMensagem")
        ))

        # ── Verifica status do contrato ────────────────────────────────────────
        try:
            situacao = driver.find_element(
                By.ID, "ctl00_Conteudo_grdBuscaAvancada_ctl02_lnkCD_Situacao_Cobranca"
            ).text.strip().upper()
        except NoSuchElementException:
            log(f"CPF {cpf[:3]}*** sem contrato ativo no CNY.", modulo=MODULO)
            return False

        if situacao in _STATUS_PAGO:
            log(f"Contrato QUITADO no CNY (status: {situacao}).", "SUCCESS", MODULO)
            return True

        if situacao in _STATUS_IGNORAR:
            log(f"Contrato com status {situacao} — nao cobrar.", modulo=MODULO)
            return True  # retorna True para pular a cobrança também

        # ── Entra no contrato e vai à tabela de boletos ────────────────────────
        driver.find_element(
            By.ID, "ctl00_Conteudo_grdBuscaAvancada_ctl02_lnkID_Documento"
        ).click()
        wait.until(EC.element_to_be_clickable((By.ID, "ctl00_Conteudo_btnConfirma"))).click()
        wait.until(EC.presence_of_element_located(
            (By.ID, "ctl00_Conteudo_identificacao_cota_btnLocaliza")))

        btn = driver.find_element(By.ID, "ctl00_Conteudo_identificacao_cota_btnLocaliza")
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(4)

        tabela = wait.until(EC.presence_of_element_located(
            (By.ID, "ctl00_Conteudo_grdBoleto_Avulso")))
        linhas = tabela.find_elements(By.TAG_NAME, "tr")

        # ── Procura a linha com o vencimento informado ─────────────────────────
        # vencimento vem no formato DD/MM/YYYY
        for linha in linhas:
            colunas = linha.find_elements(By.TAG_NAME, "td")
            if len(colunas) <= 4:
                continue
            venc_linha = colunas[4].text.strip()
            if venc_linha != vencimento:
                continue

            # Linha encontrada — verifica se tem checkbox de emissão
            checkboxes = linha.find_elements(
                By.CSS_SELECTOR, "input[id*='imgEmite_Boleto']")
            if not checkboxes:
                # Sem checkbox = boleto já foi emitido e possivelmente quitado
                log(f"Boleto {vencimento} sem opcao de emissao — considerado pago.", "SUCCESS", MODULO)
                return True

            src = checkboxes[0].get_attribute("src") or ""
            if "ckUnchecked" not in src:
                # Checkbox não está desmarcado = já processado
                log(f"Boleto {vencimento} ja processado no CNY.", "SUCCESS", MODULO)
                return True

            log(f"Boleto {vencimento} ainda em aberto no CNY.", modulo=MODULO)
            return False

        # Linha com esse vencimento não encontrada — não há boleto em aberto
        log(f"Boleto {vencimento} nao encontrado na tabela CNY — possivel quitacao.", modulo=MODULO)
        return True

    except (TimeoutException, WebDriverException) as e:
        log(f"Erro ao verificar CNY: {e}", "WARNING", MODULO)
        return False  # em caso de erro, cobra normalmente
    except Exception as e:
        log(f"Erro inesperado na verificacao CNY: {e}", "WARNING", MODULO)
        return False
