# Instale as dependências via terminal com o comando abaixo antes de rodar:
# pip install selenium pandas openpyxl

import os
import time
import re
import urllib.parse
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

def setup_driver(headless=False):
    """
    Configura o Selenium WebDriver com opções otimizadas para Docker/Render.
    Inclui opções de estabilidade para ambientes com pouca memória.
    """
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    
    # Flags essenciais para Docker/containers com pouca memória
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--single-process")           # Crítico para Render free tier
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")           # Não carrega imagens → muito mais rápido
    options.add_argument("--window-size=1280,800")
    options.add_argument("--memory-pressure-off")
    options.add_argument("--max_old_space_size=256")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-default-apps")
    options.add_argument("--mute-audio")
    
    # Técnicas de evasão (mantidas)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Caminhos para Docker
    chrome_bin = os.environ.get("CHROME_BIN")
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")
    
    if chrome_bin:
        options.binary_location = chrome_bin
    
    # Retry: tenta até 2 vezes inicializar o driver
    for attempt in range(2):
        try:
            if chromedriver_path and os.path.exists(chromedriver_path):
                service = Service(executable_path=chromedriver_path)
                driver = webdriver.Chrome(service=service, options=options)
            else:
                driver = webdriver.Chrome(options=options)
            
            # Esconde o "webdriver = true"
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
            driver.set_page_load_timeout(30)
            driver.set_script_timeout(15)
            return driver
        except Exception as e:
            if attempt == 0:
                time.sleep(2)  # Aguarda e tenta de novo
            else:
                raise e


def inferir_whatsapp(telefone):
    """ Tenta detectar se o número é de celular brasileiro e gera link direto de WhatsApp. """
    if not telefone or telefone == "Não encontrado":
        return "Sem WhatsApp"
    
    # Capturar apenas dígitos numéricos
    digitos = re.sub(r'\D', '', telefone)
    
    # Validar formato brasileiro (Tirar DDI nacional)
    if digitos.startswith("55") and len(digitos) > 11:
        digitos = digitos[2:]
    elif digitos.startswith("0") and len(digitos) > 10:
        digitos = digitos[1:]
        
    # Celular brasileiro com DDD geralmente tem 11 dígitos e o terceiro dígito (após DDD) é 9
    if len(digitos) == 11 and digitos[2] == '9':
        return f"https://wa.me/55{digitos}"
    
    return "Parece Telefone Fixo (Ou 0800)"

def scrape_google_maps(keyword, headless=False, log_callback=None, max_results=None, min_rating=None, site_filter='todos', cancel_event=None):
    """
    Realiza o web scraping no Google Maps buscando pela palavra-chave com mais detalhes.
    Suporta interrupção, limite numérico e filtro de presença de website.
    """
    def _log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    driver = setup_driver(headless)
    wait = WebDriverWait(driver, 10)
    
    url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(keyword)}"
    _log(f"[{keyword}] Acessando o Google Maps...")
    driver.get(url)
    
    contacts = []
    
    try:
        feed_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='feed']")))
        _log(f"[{keyword}] Lista de resultados encontrada. Iniciando rolagem (bypass bloqueios)...")
        
        try:
            last_height = driver.execute_script("return arguments[0].scrollHeight", feed_container)
        except Exception:
            last_height = 0
        
        # Otimização: se só quer N resultados sem filtros, para bem cedo no scroll
        # Com filtros, precisa rolar mais, mas também limita
        can_skip_scroll = (
            max_results == 1 and 
            site_filter == 'todos' and 
            min_rating is None
        )
        
        # Multiplier: com filtros, precisamos de mais candidatos para compensar os rejeitados
        scroll_buffer = 5 if not (site_filter != 'todos' or min_rating) else (max_results or 10) * 4
        
        if can_skip_scroll:
            _log(f"[{keyword}] Qtd. máxima=1 → Pulando rolagem, pegando primeiro resultado direto.")
        else:
            while True:
                if cancel_event and cancel_event.is_set():
                    _log(f"[{keyword}] Operação de rolagem interrompida pelo usuário.")
                    break
                
                try:
                    driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight)", feed_container)
                except Exception:
                    _log(f"[{keyword}] Erro de scroll, encerrando rolagem.")
                    break
                    
                time.sleep(1.5)
                
                try:
                    new_height = driver.execute_script("return arguments[0].scrollHeight", feed_container)
                except Exception:
                    break
                
                try:
                    end_of_list = driver.find_element(By.XPATH, "//*[contains(text(), 'Você chegou ao fim da lista') or contains(text(), \"You've reached the end of the list\")]")
                    if end_of_list.is_displayed():
                        _log(f"[{keyword}] Fim da lista detectado com sucesso.")
                        break
                except NoSuchElementException:
                    pass
                    
                # Parar cedo com base na quantidade de itens visíveis
                if max_results:
                    items_temp = feed_container.find_elements(By.CSS_SELECTOR, "a[href*='/maps/place/']")
                    if len(items_temp) >= max_results + scroll_buffer:
                        _log(f"[{keyword}] Itens suficientes ({len(items_temp)}) para atingir meta. Parando rolagem.")
                        break

                if new_height == last_height:
                    try:
                        feed_container.send_keys(Keys.PAGE_DOWN)
                        time.sleep(1.5)
                    except Exception:
                        pass
                    
                    try:
                        new_height = driver.execute_script("return arguments[0].scrollHeight", feed_container)
                    except Exception:
                        break
                        
                    if new_height == last_height:
                        _log(f"[{keyword}] Sem mais resultados para carregar na rolagem.")
                        break
                        
                last_height = new_height
            
        _log(f"[{keyword}] Rolagem concluída. Extraindo estabelecimentos agora...")
        
        items = feed_container.find_elements(By.CSS_SELECTOR, "a[href*='/maps/place/']")
        unique_urls = list(set([item.get_attribute("href") for item in items if item.get_attribute("href")]))
        _log(f"[{keyword}] Encontrados {len(unique_urls)} links únicos.")
        
        for idx, item_url in enumerate(unique_urls):
            if cancel_event and cancel_event.is_set():
                _log(f"[{keyword}] Extração abortada pelo usuário no item {idx+1}.")
                break
                
            progress_str = f"[{idx+1}/{len(unique_urls)}]"
            if max_results:
                progress_str += f" (Validados: {len(contacts)}/{max_results})"
                
            _log(f"[{keyword}] Lendo estabelecimento {progress_str}...")
            driver.get(item_url)
            
            # Aguarda o título do lugar carregar em vez de sleep fixo longo
            try:
                wait.until(EC.presence_of_element_located((By.XPATH, "//h1")))
                time.sleep(0.8) # Pequena pausa para garantir carregamento de outros dados (telefone/site)
            except TimeoutException:
                _log(f"   [!] Aviso: Título não carregou a tempo para {item_url}")
            
            nome = "Não encontrado"
            telefone = "Não encontrado"
            site = "Sem site"
            classificacao = "Sem notas"
            redes_sociais = "Nenhuma"
            
            # --- Nome ---
            try:
                nome_element = wait.until(EC.presence_of_element_located((By.XPATH, "//h1")))
                nome = nome_element.text
            except TimeoutException:
                pass
                
            # --- Telefone ---
            try:
                phone_element = driver.find_element(By.CSS_SELECTOR, "[data-item-id^='phone:']")
                telefone = phone_element.text
            except NoSuchElementException:
                pass
                
            # --- Site ---
            site_links = []
            try:
                website_element = driver.find_element(By.CSS_SELECTOR, "[data-item-id='authority']")
                site = website_element.get_attribute("href")
            except NoSuchElementException:
                pass
                
            # --- Classificação (Nota/Reviews) ---
            try:
                # O Google Maps geralmente guarda a nota no topo perto do H1, no primeiro div na mesma coluna
                # Frequentemente, tem classe F7nice ou span com 'estrelas'
                rating_element = driver.find_element(By.CSS_SELECTOR, "div.F7nice")
                classificacao = rating_element.text.replace('\n', ' ')
            except NoSuchElementException:
                pass
                
            # --- Redes Sociais ---
            try:
                # Coletando todos os links da barra lateral
                todas_tags_a = driver.find_elements(By.CSS_SELECTOR, "div[role='main'] a")
                redes_detectadas = set()
                
                for a in todas_tags_a:
                    href = a.get_attribute("href")
                    if not href:
                        continue
                    if "instagram.com/" in href:
                        redes_detectadas.add("Instagram")
                    if "facebook.com/" in href:
                        redes_detectadas.add("Facebook")
                    if "linkedin.com/" in href:
                        redes_detectadas.add("LinkedIn")
                    if "twitter.com/" in href or "x.com/" in href:
                        redes_detectadas.add("Twitter/X")
                        
                if redes_detectadas:
                    redes_sociais = ", ".join(list(redes_detectadas))
            except Exception:
                pass
                
            # Formatações Finais
            if not telefone or telefone.strip() == "":
                telefone = "Não encontrado"
            if not site or site.strip() == "":
                site = "Sem site"
            
            link_whatsapp = inferir_whatsapp(telefone)
            
            # --- Filtros de Inclusão ---
            has_site = (site != "Sem site")
            if site_filter == 'com_site' and not has_site:
                continue
            if site_filter == 'sem_site' and has_site:
                continue
                
            # --- Filtro de Classificação (Nota Mínima) ---
            if min_rating is not None:
                if classificacao == "Sem notas":
                    if min_rating > 0:
                        continue # Rejeita local sem review
                else:
                    try:
                        # Extrai os dígitos primários (ex: '4,8' de '4,8 (120)') e converte pra float
                        nota_str = classificacao.split(' ')[0].replace(',', '.')
                        nota_float = float(nota_str)
                        if nota_float < min_rating:
                            continue # Rejeita notas menores que o limiar
                    except Exception:
                        pass # Falha rara no parseamento, deixa passar.
                
            contacts.append({
                "Nome": nome,
                "Telefone": telefone,
                "Link_WhatsApp": link_whatsapp,
                "Site": site,
                "Redes_Sociais": redes_sociais,
                "Classificacao": classificacao,
                "URL_Maps": item_url
            })
            
            # --- Limite de Resultados ---
            if max_results and len(contacts) >= max_results:
                _log(f"[{keyword}] Limite atingido: {max_results} leads validados processados com sucesso.")
                break
            
    except Exception as e:
        _log(f"[{keyword}] Um erro ocorreu durante a captura: {e}")
    finally:
        driver.quit()
        
    return contacts

def remover_duplicatas_e_salvar(data, filename="resultados.xlsx", log_callback=None):
    """
    Usa o Pandas para remover registros repetidos e gerar o arquivo de saída.
    """
    def _log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    if not data:
        _log("Nenhum dado extraído para tratamento.")
        return None
        
    df = pd.DataFrame(data)
    qtd_inicial = len(df)
    
    df.drop_duplicates(subset=["Nome", "Telefone"], keep="first", inplace=True)
    qtd_final = len(df)
    
    # Melhoria na ordenação das colunas do Excel
    ordem_colunas = ['Nome', 'Telefone', 'Link_WhatsApp', 'Classificacao', 'Site', 'Redes_Sociais', 'URL_Maps']
    df = df.reindex(columns=[c for c in ordem_colunas if c in df.columns])
    
    _log(f"Processamento: {qtd_inicial - qtd_final} locais repetidos removidos.")
    
    if filename.endswith('.csv'):
        df.to_csv(filename, index=False, encoding='utf-8-sig')
    else:
        df.to_excel(filename, index=False)
        
    _log(f"--> SUCESSO! Mágica finalizada! Arquivo com {qtd_final} registros salvo.")
    return filename

if __name__ == "__main__":
    PALAVRA_CHAVE = "Pizzaria em Niterói"
    RODAR_OCULTO = False 
    NOME_DO_ARQUIVO = "prospeccao_teste.xlsx"
    
    print("-" * 60)
    print("INICIANDO BOT STEALTH COM GOOGLE MAPS")
    print(f"Alvo: {PALAVRA_CHAVE}")
    print("-" * 60)
    
    dados_extraidos = scrape_google_maps(PALAVRA_CHAVE, headless=RODAR_OCULTO)
    remover_duplicatas_e_salvar(dados_extraidos, NOME_DO_ARQUIVO)

