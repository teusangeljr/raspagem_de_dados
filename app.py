import os
import re
import json
import queue
import threading
import time
import urllib.request
from datetime import datetime
from flask import Flask, render_template, request, Response, jsonify, send_file
from google_maps_scraper import scrape_google_maps, remover_duplicatas_e_salvar

GEMINI_API_KEY = "AIzaSyCT4_yoLvQZWt8PFF3mJk2YtKIjd_8QhRk"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

app = Flask(__name__)

# ─────────────────────────────────────────────
#  Estado global da aplicação
# ─────────────────────────────────────────────

status_queue  = queue.Queue()
download_files = {}          # keyword → filepath
cancel_event  = threading.Event()
scraper_lock  = threading.Lock() # Trava de segurança para impedir múltiplas instâncias de Chrome (Render Free)

session_stats = {
    "total_leads":   0,
    "keywords_done": 0,
    "start_time":    None,
    "leads_per_min": 0.0,
}
session_history = []          # lista de sessões anteriores salvas em memória
last_leads      = []          # últimos leads coletados (para a página /leads)


# ─────────────────────────────────────────────
#  Thread de scraping
# ─────────────────────────────────────────────

def scraper_thread(keywords, headless, max_results, min_rating, site_filter, country, q, cancel_signal):
    """
    Processa uma ou mais palavras-chave em sequência.
    Emite mensagens de progresso na fila `q`.
    """
    global session_stats, session_history, last_leads, scraper_lock
    
    if not scraper_lock.acquire(blocking=False):
        q.put("❌ Já existe uma prospecção em andamento. No Render Free, permitimos apenas uma por vez para evitar quedas.")
        q.put("DONE|ERROR")
        return

    try:
        session_stats["start_time"]    = time.time()
        session_stats["total_leads"]   = 0
        session_stats["keywords_done"] = 0
        last_leads.clear()

        all_data = []
        total_keywords = len(keywords)

        def log_pusher(msg):
            q.put(msg)
            elapsed = time.time() - session_stats["start_time"]
            lpm = (session_stats["total_leads"] / elapsed * 60) if elapsed > 0 else 0
            session_stats["leads_per_min"] = round(lpm, 1)

        for kw_index, keyword in enumerate(keywords, start=1):
            if cancel_signal.is_set():
                q.put(f"⛔ Operação cancelada antes de processar: {keyword}")
                break

            q.put(f"🔑 [{kw_index}/{total_keywords}] Iniciando busca por: \"{keyword}\"")

            try:
                search_keyword = f"{keyword} {country}".strip() if country else keyword

                data = scrape_google_maps(
                    keyword=search_keyword,
                    headless=headless,
                    log_callback=log_pusher,
                    max_results=max_results,
                    min_rating=min_rating,
                    site_filter=site_filter,
                    cancel_event=cancel_signal,
                )

                leads_found = len(data)
                session_stats["total_leads"]   += leads_found
                session_stats["keywords_done"] += 1
                all_data.extend(data)

                elapsed = time.time() - session_stats["start_time"]
                stats_payload = {
                    "total_leads":    session_stats["total_leads"],
                    "keywords_done":  session_stats["keywords_done"],
                    "total_keywords": total_keywords,
                    "leads_per_min":  session_stats["leads_per_min"],
                    "elapsed_sec":    int(elapsed),
                }
                q.put(f"STATS|{json.dumps(stats_payload)}")

            except Exception as e:
                q.put(f"❌ Erro ao processar \"{keyword}\": {e}")

        if cancel_signal.is_set() and not all_data:
            q.put("DONE|CANCELED")
            return

        # ── Salva resultado final ────────────────────────────────────────────────
        try:
            kw_slug = "_".join(kw.replace(' ', '-').lower() for kw in keywords[:3])
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename  = f"leads_{kw_slug}_{timestamp}.xlsx"

            result_file = remover_duplicatas_e_salvar(all_data, filename=filename, log_callback=log_pusher)

            if result_file:
                download_files["last"] = result_file

                # Salva leads em memória
                last_leads.clear()
                last_leads.extend(all_data)

                # Registra na história de sessões (incluindo os leads para rever)
                session_history.append({
                    "id":          int(time.time()),
                    "timestamp":   datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "keywords":    keywords,
                    "total_leads": session_stats["total_leads"],
                    "filename":    result_file,
                    "leads":       list(all_data) # Snapshot dos leads
                })

                q.put(f"DONE|{result_file}")
            else:
                q.put("DONE|ERROR")

        except Exception as e:
            q.put(f"❌ Erro ao salvar arquivo: {e}")
            q.put("DONE|ERROR")
    finally:
        if scraper_lock.locked():
            scraper_lock.release()


# ─────────────────────────────────────────────
#  Rotas
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/leads')
def leads_page():
    return render_template('leads.html')


@app.route('/api/leads')
def api_leads():
    return jsonify(last_leads)


@app.route('/api/generate_copy', methods=['POST'])
def generate_copy():
    lead = request.json or {}
    nome       = lead.get('Nome', 'o estabelecimento')
    categoria  = lead.get('Categoria', 'negócio local')
    endereco   = lead.get('Endereco', '')
    classif    = lead.get('Classificacao', '')
    site       = lead.get('Site', 'Sem site')
    redes      = lead.get('Redes_Sociais', '')
    tem_site   = site and site != 'Sem site'

    prompt = f"""Você é um especialista em copywriting e prospecção B2B para agência de marketing digital. \
Baseado nos dados do estabelecimento abaixo, gere textos altamente persuasivos e personalizados focados em vender serviços de marketing, sites e gestão.

DADOS DO ESTABELECIMENTO:
- Nome: {nome}
- Categoria: {categoria}
- Localização: {endereco or 'Não informada'}
- Avaliação no Google: {classif or 'Não informada'}
- Tem site: {'Sim — já está online' if tem_site else 'Não — GRANDE oportunidade!'}
- Redes sociais ativas: {redes if redes and redes != 'Nenhuma' else 'Nenhuma detectada'}

Gere 7 tipos de copy, todos personalizados para este negócio específico em Português do Brasil:

1. PRIMEIRA_MENSAGEM: Abordagem inicial fria pelo WhatsApp ou Instagram DM. Tom natural, direto, não invasivo. Crie conexão e desperte curiosidade sem revelar tudo. Máx 160 palavras.
2. PROMOCAO: Oferta irresistível com tempo limitado para o nicho deles. Tom urgente, escassez, benefício claro. Máx 120 palavras.
3. LANDING_PAGE: Headline, Subtítulo, Corpo e CTA para uma página de vendas. Atente-se à persuasão.
4. SISTEMA: Proposta para vender agendamento online ou CRM específico para {categoria}. Nos problemas que resolve e no ROI.
5. ARTE_CRIATIVO: Briefing para post de Instagram (Tema e Legenda com emojis).
6. VIDEO: Script de Reels/Stories (30s) com Gancho, Conteúdo e CTA.
7. DESIGNER: Proposta de renovação de marca e identidade visual.

IMPORTANTE: Retorne APENAS um JSON válido. Formato exato:
{{"primeira_mensagem":"","promocao":"","landing_page":"","sistema":"","arte_criativo":"","video":"","designer":""}}"""

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 4096}
    }).encode('utf-8')

    try:
        req = urllib.request.Request(GEMINI_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        raw_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        raw_text = re.sub(r'^```[a-z]*\n?', '', raw_text)
        raw_text = re.sub(r'\n?```$', '', raw_text).strip()
        copy_data = json.loads(raw_text)
        return jsonify({"success": True, "copy": copy_data})
    except Exception as e:
        print(f"Erro Gemini API: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/start_scrape', methods=['POST'])
def start_scrape():
    global status_queue, cancel_event, scraper_lock
    
    if scraper_lock.locked():
        return jsonify({"error": "Já existe uma prospecção rodando. Aguarde terminar para iniciar outra (limite do servidor free)."}), 429

    data = request.json or {}
    raw_kw = data.get('keyword', '')
    if isinstance(raw_kw, list):
        keywords = [k.strip() for k in raw_kw if k.strip()]
    else:
        keywords = [k.strip() for k in raw_kw.split(',') if k.strip()]

    if not keywords:
        return jsonify({"error": "Informe ao menos uma palavra-chave."}), 400

    headless    = data.get('headless',    True)
    max_results = data.get('max_results', None)
    min_rating  = data.get('min_rating',  None)
    site_filter = data.get('site_filter', 'todos')
    country     = data.get('country', '')

    if max_results is not None:
        try: max_results = int(max_results)
        except: max_results = None
    if min_rating is not None:
        try: min_rating = float(min_rating)
        except: min_rating = None

    while not status_queue.empty():
        try: status_queue.get_nowait()
        except queue.Empty: break

    cancel_event.clear()
    thread = threading.Thread(
        target=scraper_thread,
        args=(keywords, headless, max_results, min_rating, site_filter, country, status_queue, cancel_event),
        daemon=True,
    )
    thread.start()
    return jsonify({"status": "started", "keywords": keywords})


@app.route('/api/cancel_scrape')
def cancel_scrape():
    cancel_event.set()
    return jsonify({"status": "canceling"})


@app.route('/api/scrape_stream')
def scrape_stream():
    def event_stream():
        while True:
            try:
                # Timeout curto (15s) para enviar keep-alive e evitar queda de conexão
                msg = status_queue.get(timeout=15)
                yield f"data: {msg}\n\n"
                if msg.startswith("DONE|"): break
            except queue.Empty:
                # Envia comentário de keep-alive para manter a conexão ativa
                yield ": keep-alive\n\n"
    return Response(event_stream(), mimetype="text/event-stream")


@app.route('/api/download')
def download():
    filepath = download_files.get("last")
    if filepath and os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({"error": "Nenhum arquivo disponível"}), 404


@app.route('/api/download_csv')
def download_csv():
    filepath = download_files.get("last", "")
    csv_path  = filepath.replace('.xlsx', '.csv') if filepath else ""
    if csv_path and os.path.exists(csv_path):
        return send_file(csv_path, as_attachment=True)
    return jsonify({"error": "CSV não encontrado"}), 404


# ─── Gerenciamento de Histórico ───────────────────────────────────────────

@app.route('/api/history')
def history():
    # Retorna o histórico omitindo os leads (pesado demais para o list view)
    history_view = []
    for item in session_history:
        history_view.append({
            "id":          item.get("id"),
            "timestamp":   item.get("timestamp"),
            "keywords":    item.get("keywords"),
            "total_leads": item.get("total_leads"),
            "filename":    item.get("filename")
        })
    return jsonify(history_view[-30:]) # Últimas 30


@app.route('/api/history/select/<int:sess_id>')
def history_select(sess_id):
    global last_leads
    for item in session_history:
        if item.get("id") == sess_id:
            last_leads = list(item.get("leads", []))
            return jsonify({"success": True})
    return jsonify({"success": False, "error": "Sessão não encontrada"}), 404


@app.route('/api/history/delete/<int:sess_id>', methods=['DELETE'])
def history_delete(sess_id):
    global session_history
    session_history = [s for s in session_history if s.get("id") != sess_id]
    return jsonify({"success": True})


@app.route('/api/history/clear', methods=['DELETE'])
def history_clear():
    global session_history
    session_history = []
    return jsonify({"success": True})


@app.route('/api/history/download/<filename>')
def history_download(filename):
    # Apenas envia o arquivo se ele existir no diretório raiz
    if os.path.exists(filename):
        return send_file(filename, as_attachment=True)
    return jsonify({"error": "Arquivo não encontrado"}), 404


@app.route('/api/stats')
def stats():
    elapsed = 0
    if session_stats["start_time"]:
        elapsed = int(time.time() - session_stats["start_time"])
    return jsonify({**session_stats, "elapsed_sec": elapsed})


if __name__ == '__main__':
    app.run(debug=True, threaded=True, port=5000)
