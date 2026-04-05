# Instale as dependências via terminal com o comando abaixo antes de rodar:
# pip install selenium pandas openpyxl

import time
import re
import random
import urllib.parse
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.remote_connection import RemoteConnection
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from urllib3.exceptions import ProtocolError

# Note: Timeouts are handled at the driver instance level in setup_driver


# ─────────────────────────────────────────────
#  CONFIGURAÇÃO DO DRIVER
# ─────────────────────────────────────────────

def setup_driver(headless=False):
    """
    Configura o Selenium WebDriver com técnicas avançadas de evasão anti-bot.
    Usa o Selenium Manager nativo (4.6+) — não precisa do webdriver_manager.
    """
    options = Options()
    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    # Otimização agressiva de cache e memória para o Render (0.1 CPU)
    options.add_argument("--disk-cache-size=1")
    options.add_argument("--media-cache-size=1")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-gpu-shader-disk-cache")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")
    options.add_argument("--lang=pt-BR")

    # Otimização de Memória e CPU (Render-friendly)
    options.add_argument("--disable-features=Translate,OptimizationHints,OptimizationGuide,OptimizationGuideFetching,OptimizationTargetPrediction")
    options.add_argument("--disable-browser-side-navigation")
    options.add_argument("--dns-prefetch-disable")
    
    # NOVAS FLAGS PARA ESTABILIDADE NO RENDER (Removido os lentos e instáveis)
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--js-flags='--expose-gc'") 
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-canvas-aa")
    options.add_argument("--disable-2d-canvas-clip-utils")
    options.add_argument("--disable-gl-drawing-for-tests")
    options.add_argument("--remote-debugging-port=9222")

    # DESATIVA CARREGAMENTO DE IMAGENS E CSS PARA GANHAR PERFORMANCE AGRESSIVA
    prefs = {
        "profile.managed_default_content_settings.images": 2, 
        "profile.managed_default_content_settings.stylesheets": 2,
        "profile.managed_default_content_settings.fonts": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    options.add_experimental_option("prefs", prefs)

    # DESATIVA CARREGAMENTO DE IMAGENS PARA GANHAR PERFORMANCE
    # 2 = Block images
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

    # Rotaciona user-agents para reduzir detecção de padrão
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]
    options.add_argument(f"user-agent={random.choice(user_agents)}")

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # BLOQUEIO DE RECURSOS PARA MAXIMIZAR VELOCIDADE (Render Production Mode)
    # Bloqueia Imagens (já estava), mas agora também CSS (opcional, vamos manter por segurança se a estrutura quebrar, mas vamos desativar fonts)
    prefs = {
        "profile.managed_default_content_settings.images": 2, # Block images
        "profile.default_content_setting_values.notifications": 2,
        "profile.managed_default_content_settings.stylesheets": 2, # BLOQUEIA CSS (Ganho de 40% de velocidade)
        "profile.managed_default_content_settings.fonts": 2,       # BLOQUEIA FONTS
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)

    # Remove timeout de carregamento de página (sem limite)
    driver.set_page_load_timeout(300)   # 5 min máximo por página
    driver.set_script_timeout(300)      # 5 min máximo por script

    # Injeta script para ocultar rastreios de automação
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
            Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en-US']});
        """
    })

    return driver


# ─────────────────────────────────────────────
#  UTILITÁRIOS
# ─────────────────────────────────────────────

def _safe_wait(driver, by, selector, timeout=60, retries=3):
    """
    Tenta localizar um elemento com múltiplas tentativas e backoff exponencial.
    Retorna o elemento ou None se não encontrar.
    """
    wait = WebDriverWait(driver, timeout)
    for attempt in range(1, retries + 1):
        try:
            return wait.until(EC.presence_of_element_located((by, selector)))
        except TimeoutException:
            if attempt < retries:
                sleep_time = attempt * 2 + random.uniform(0.5, 1.5)
                time.sleep(sleep_time)
    return None


def _find_safe(driver, by, selector):
    """find_element sem lançar exceção — retorna None se não encontrar."""
    try:
        return driver.find_element(by, selector)
    except NoSuchElementException:
        return None


def _human_pause(base=1.0, variance=0.8):
    """Pausa aleatória que imita comportamento humano."""
    time.sleep(base + random.uniform(0, variance))


def inferir_whatsapp(telefone):
    """Detecta se o número é celular brasileiro e gera link direto de WhatsApp."""
    if not telefone or telefone == "Não encontrado":
        return "Sem WhatsApp"

    digitos = re.sub(r'\D', '', telefone)

    if digitos.startswith("55") and len(digitos) > 11:
        digitos = digitos[2:]
    elif digitos.startswith("0") and len(digitos) > 10:
        digitos = digitos[1:]

    if len(digitos) == 11 and digitos[2] == '9':
        return f"https://wa.me/55{digitos}"

    return "Parece Telefone Fixo (Ou 0800)"


def calcular_score_lead(registro):
    """
    Pontua a qualidade do lead de 0 a 100 com base nos dados disponíveis.
    Critérios:
      - Tem telefone celular       → +30
      - Tem telefone fixo          → +15
      - Tem site                   → +20
      - Tem nota (reviews)         → +15
      - Nota ≥ 4.0                 → +10 bônus
      - Tem endereço               → +10
      - Tem redes sociais          → +10
      - Tem horário de func.       → +5
    """
    score = 0
    tel = registro.get("Telefone", "")
    wa  = registro.get("Link_WhatsApp", "")
    site = registro.get("Site", "Sem site")
    nota_raw = registro.get("Classificacao", "Sem notas")
    endereco = registro.get("Endereco", "")
    redes = registro.get("Redes_Sociais", "Nenhuma")
    horario = registro.get("Horario", "")

    if wa and "wa.me" in wa:
        score += 30
    elif tel and tel != "Não encontrado":
        score += 15

    if site and site != "Sem site":
        score += 20

    if nota_raw and nota_raw != "Sem notas":
        score += 15
        try:
            nota_float = float(nota_raw.split(' ')[0].replace(',', '.'))
            if nota_float >= 4.0:
                score += 10
        except Exception:
            pass

    if endereco and endereco != "Não encontrado":
        score += 10

    if redes and redes != "Nenhuma":
        score += 10

    if horario and horario != "Não encontrado":
        score += 5

    return min(score, 100)


def extrair_coordenadas(url):
    """Extrai latitude e longitude da URL do Google Maps quando disponível."""
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match:
        return match.group(1), match.group(2)
    return "N/A", "N/A"


# ─────────────────────────────────────────────
#  SCRAPER PRINCIPAL
# ─────────────────────────────────────────────

def scrape_google_maps(
    keyword,
    headless=False,
    log_callback=None,
    max_results=None,
    min_rating=None,
    site_filter='todos',
    cancel_event=None
):
    """
    Realiza o web scraping no Google Maps buscando pela palavra-chave.

    Parâmetros:
      keyword     : Termo de busca (ex: "Pizzaria em Niterói")
      headless    : Rodar sem janela gráfica
      log_callback: Função chamada a cada mensagem de log
      max_results : Limite máximo de leads válidos a retornar
      min_rating  : Nota mínima aceitável (float). None = sem filtro.
      site_filter : 'todos' | 'com_site' | 'sem_site'
      cancel_event: threading.Event() — seta para cancelar a operação

    Retorna lista de dicts com os dados de cada estabelecimento.
    """
    def _log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    driver = setup_driver(headless)
    wait   = WebDriverWait(driver, 60)  # sem timeout agressivo
    contacts = []

    url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(keyword)}"
    _log(f"[{keyword}] 🌐 Acessando o Google Maps...")

    try:
        driver.get(url)
        _human_pause(2, 1)

        # ── Aguarda o feed de resultados ──────────────────────────────────────
        feed_container = _safe_wait(driver, By.CSS_SELECTOR, "div[role='feed']", timeout=60, retries=3)
        if not feed_container:
            _log(f"[{keyword}] ❌ Não foi possível carregar a lista de resultados.")
            return contacts

        _log(f"[{keyword}] 📋 Lista encontrada. Iniciando rolagem...")

        # ── Rolagem para carregar todos os resultados ──────────────────────────
        last_height = driver.execute_script("return arguments[0].scrollHeight", feed_container)
        scroll_stuck_count = 0

        while True:
            if cancel_event and cancel_event.is_set():
                _log(f"[{keyword}] ⛔ Rolagem interrompida pelo usuário.")
                break

            driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight)", feed_container)
            # Reduzido para 1.5s (estava 2.2s) para acelerar a rolagem em rede estável
            _human_pause(1.5, 0.4) 

            new_height = driver.execute_script("return arguments[0].scrollHeight", feed_container)

            # Detecta fim de lista em PT e EN
            try:
                end_markers = [
                    "//*[contains(text(), 'Você chegou ao fim da lista')]",
                    "//*[contains(text(), \"You've reached the end of the list\")]",
                    "//*[contains(text(), 'No more results')]",
                ]
                for xpath in end_markers:
                    el = driver.find_elements(By.XPATH, xpath)
                    if el and el[0].is_displayed():
                        _log(f"[{keyword}] ✅ Fim da lista detectado.")
                        break
                else:
                    pass
                # Se o loop interno quebrou por break, precisa sair do while também
                # Vamos re-verificar usando flag
            except Exception:
                pass

            # Verifica se já coletamos itens suficientes para parar a rolagem cedo
            # (Render Speedup: Se já temos itens em cache suficientes para cumprir o max_results * 1.5, paramos)
            if max_results:
                items_temp = feed_container.find_elements(By.CSS_SELECTOR, "a[href*='/maps/place/']")
                multiplier = 1.2 if (site_filter == 'todos' and min_rating is None) else 4.0
                if len(items_temp) >= max_results * multiplier:
                    _log(f"[{keyword}] 🎯 Link caches suficientes ({len(items_temp)}). Parando rolagem cedo.")
                    break

            if new_height == last_height:
                scroll_stuck_count += 1
                if scroll_stuck_count >= 3:
                    _log(f"[{keyword}] ℹ️ Sem novos resultados após {scroll_stuck_count} tentativas.")
                    break
                # Tenta forçar via teclado
                try:
                    feed_container.send_keys(Keys.END)
                    _human_pause(1.5, 0.8)
                except Exception:
                    pass
            else:
                scroll_stuck_count = 0

            last_height = new_height

            # SEGURANÇA: Se a rolagem estiver demorando demais e já tivermos o dobro do limite, avançamos
            if max_results and len(items_temp) >= max_results * 2.5:
                break

        _log(f"[{keyword}] 🔍 Extraindo links dos estabelecimentos...")

        items = feed_container.find_elements(By.CSS_SELECTOR, "a[href*='/maps/place/']")
        unique_urls = list(dict.fromkeys(
            item.get_attribute("href") for item in items if item.get_attribute("href")
        ))
        _log(f"[{keyword}] 🗺️  {len(unique_urls)} links únicos encontrados.")

        # ── Visita cada estabelecimento com sistema de auto-recuperação ────────────
        current_idx = 0
        while current_idx < len(unique_urls):
            item_url = unique_urls[current_idx]
            try:
                if cancel_event and cancel_event.is_set():
                    _log(f"[{keyword}] ⛔ Extração abortada no item {current_idx + 1}.")
                    break

                progress = f"[{current_idx + 1}/{len(unique_urls)}]"
                if max_results:
                    progress += f" (Validados: {len(contacts)}/{max_results})"
                _log(f"[{keyword}] 📍 Lendo estabelecimento {progress}...")

                # Navegação robusta
                page_loaded = False
                for nav_attempt in range(1, 3):
                    try:
                        driver.get(item_url)
                        h1_el = _safe_wait(driver, By.XPATH, "//h1", timeout=35, retries=1)
                        if h1_el:
                            page_loaded = True
                            break
                        _human_pause(1.5, 0.5)
                    except (WebDriverException, ProtocolError, Exception) as e:
                        if "localhost" in str(e).lower() or "timeout" in str(e).lower():
                            raise # Re-lança para reiniciar o driver
                        _human_pause(nav_attempt * 2, 1)

                if not page_loaded:
                    _log(f"[{keyword}]   ❌ Ignorado (timeout h1).")
                    current_idx += 1
                    continue

                # Extração rápida simplificada
                _human_pause(0.8, 0.4)
                
                nome = "Não encontrado"
                try: nome = driver.find_element(By.XPATH, "//h1").text.strip()
                except: pass

                telefone = "Não encontrado"
                try:
                    el = _find_safe(driver, By.CSS_SELECTOR, "[data-item-id^='phone:']")
                    if el: telefone = el.text.strip()
                except: pass

                site = "Sem site"
                try:
                    el = _find_safe(driver, By.CSS_SELECTOR, "[data-item-id='authority']")
                    if el: site = el.get_attribute("href").strip()
                except: pass

                endereco = "Não encontrado"
                try:
                    el = _find_safe(driver, By.CSS_SELECTOR, "[data-item-id^='address']")
                    if el: endereco = el.text.strip()
                except: pass

                categoria = "Não encontrado"
                try:
                    el = _find_safe(driver, By.CSS_SELECTOR, "div.LBgpqf button")
                    if el: categoria = el.text.strip()
                except: pass

                classificacao = "Sem notas"
                num_avaliacoes = "0"
                try:
                    el = _find_safe(driver, By.CSS_SELECTOR, "div.F7nice")
                    if el:
                        raw = el.text.replace('\n', ' ').strip()
                        classificacao = raw
                        match = re.search(r'\(([0-9.,]+)\)', raw)
                        if match: num_avaliacoes = match.group(1).replace('.', '').replace(',', '')
                except: pass

                # Redes sociais simplificado
                instagram_url = ""
                redes_detectadas = set()
                try:
                    tags_a = driver.find_elements(By.CSS_SELECTOR, "div[role='main'] a")
                    for a in tags_a:
                        href = a.get_attribute("href") or ""
                        if "instagram.com/" in href: 
                            redes_detectadas.add("Instagram")
                            if not instagram_url: instagram_url = href.split('?')[0].rstrip('/')
                        elif "facebook.com/" in href: redes_detectadas.add("Facebook")
                except: pass

                redes_sociais = ", ".join(sorted(redes_detectadas)) if redes_detectadas else "Nenhuma"
                lat, lng = extrair_coordenadas(item_url)
                link_whatsapp = "https://wa.me/" + re.sub(r'\D', '', telefone) if telefone and telefone != "Não encontrado" else ""

                # Filtros
                has_site = site != "Sem site"
                if not (site_filter == 'com_site' and not has_site) and not (site_filter == 'sem_site' and has_site):
                    registro = {
                        "Nome": nome, "Categoria": categoria, "Telefone": telefone, 
                        "Link_WhatsApp": link_whatsapp, "Instagram_URL": instagram_url,
                        "Site": site, "Redes_Sociais": redes_sociais, "Classificacao": classificacao,
                        "Num_Avaliacoes": num_avaliacoes, "Endereco": endereco, "Horario": "Consultar Maps",
                        "Latitude": lat, "Longitude": lng, "URL_Maps": item_url
                    }
                    registro["Score_Lead"] = calcular_score_lead(registro)
                    contacts.append(registro)
                    _log(f"[{keyword}]   ✔ '{nome}' [Score: {registro['Score_Lead']}]")

                current_idx += 1
                if max_results and len(contacts) >= max_results:
                    _log(f"[{keyword}] 🏁 Limite atingido.")
                    break

            except (WebDriverException, ProtocolError, Exception) as e:
                err_msg = str(e).lower()
                if "localhost" in err_msg or "disconnected" in err_msg or "timeout" in err_msg:
                    _log(f"[{keyword}] 🔄 Conexão Localhost falhou. Reiniciando Driver para recuperar...")
                    try: driver.quit()
                    except: pass
                    driver = setup_driver(headless)
                    _log(f"[{keyword}] 🚀 Driver reiniciado. Retomando da posição {current_idx+1}...")
                    time.sleep(3)
                else:
                    _log(f"[{keyword}]   ⚠️ Erro ao processar item {current_idx+1}: {e}")
                    current_idx += 1

    except Exception as e:
        _log(f"[{keyword}] ❌ Erro inesperado: {e}")
    finally:
        driver.quit()

    _log(f"[{keyword}] 🎉 Extração concluída. Total: {len(contacts)} leads.")
    return contacts


# ─────────────────────────────────────────────
#  EXPORTAÇÃO
# ─────────────────────────────────────────────

def remover_duplicatas_e_salvar(data, filename="resultados.xlsx", log_callback=None):
    """
    Remove duplicatas, ordena por Score_Lead e salva em XLSX (e opcionalmente CSV).
    """
    def _log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    if not data:
        _log("⚠️  Nenhum dado extraído para tratamento.")
        return None

    df = pd.DataFrame(data)
    qtd_inicial = len(df)

    df.drop_duplicates(subset=["Nome", "Telefone"], keep="first", inplace=True)

    # Ordena pelos leads de maior qualidade primeiro
    if "Score_Lead" in df.columns:
        df.sort_values("Score_Lead", ascending=False, inplace=True)

    qtd_final = len(df)
    _log(f"🧹 {qtd_inicial - qtd_final} duplicata(s) removida(s). {qtd_final} leads únicos.")

    ordem_colunas = [
        'Score_Lead', 'Nome', 'Categoria', 'Telefone', 'Link_WhatsApp',
        'Classificacao', 'Num_Avaliacoes', 'Site', 'Redes_Sociais',
        'Endereco', 'Horario', 'Latitude', 'Longitude', 'URL_Maps'
    ]
    df = df.reindex(columns=[c for c in ordem_colunas if c in df.columns])

    # Salva XLSX
    if filename.endswith('.csv'):
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        _log(f"💾 CSV salvo: {filename}")
    else:
        # Salva XLSX com formatação básica de largura de coluna
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Leads')
            ws = writer.sheets['Leads']
            for col in ws.columns:
                max_len = max((len(str(cell.value or "")) for cell in col), default=10)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)
        _log(f"💾 XLSX salvo: {filename}")

        # Salva CSV junto, mesmo nome com extensão trocada
        csv_name = filename.replace('.xlsx', '.csv')
        df.to_csv(csv_name, index=False, encoding='utf-8-sig')
        _log(f"💾 CSV espelho salvo: {csv_name}")

    _log(f"✅ CONCLUÍDO! {qtd_final} leads prontos.")
    return filename


# ─────────────────────────────────────────────
#  MODO STANDALONE
# ─────────────────────────────────────────────

if __name__ == "__main__":
    PALAVRA_CHAVE  = "Pizzaria em Niterói"
    RODAR_OCULTO   = False
    NOME_DO_ARQUIVO = "prospeccao_teste.xlsx"
    LIMITE         = 20       # None = sem limite
    NOTA_MINIMA    = None     # ex: 4.0
    FILTRO_SITE    = 'todos'  # 'todos' | 'com_site' | 'sem_site'

    print("-" * 60)
    print("  BOT STEALTH — GOOGLE MAPS SCRAPER")
    print(f"  Alvo  : {PALAVRA_CHAVE}")
    print(f"  Limite: {LIMITE or 'sem limite'}")
    print("-" * 60)

    dados = scrape_google_maps(
        PALAVRA_CHAVE,
        headless=RODAR_OCULTO,
        max_results=LIMITE,
        min_rating=NOTA_MINIMA,
        site_filter=FILTRO_SITE,
    )
    remover_duplicatas_e_salvar(dados, NOME_DO_ARQUIVO)
