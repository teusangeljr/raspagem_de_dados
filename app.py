import os
import queue
import threading
from flask import Flask, render_template, request, Response, jsonify, send_file
from google_maps_scraper import scrape_google_maps, remover_duplicatas_e_salvar

app = Flask(__name__)

status_queue = queue.Queue()
download_file = None
cancel_event = threading.Event()

def scraper_thread(keyword, headless, max_results, min_rating, site_filter, q, cancel_signal):
    global download_file
    try:
        def log_pusher(msg):
            q.put(msg)
            
        # Call the scraper passing the new limits/filters and the cancellation flag
        data = scrape_google_maps(
            keyword=keyword, 
            headless=headless, 
            log_callback=log_pusher,
            max_results=max_results,
            min_rating=min_rating,
            site_filter=site_filter,
            cancel_event=cancel_signal
        )
        
        if cancel_signal.is_set() and not data:
            q.put("DONE|CANCELED")
            return
            
        # Save output
        filename = f"prospect_{keyword.replace(' ', '_').lower()}.xlsx"
        result_file = remover_duplicatas_e_salvar(data, filename=filename, log_callback=log_pusher)
        
        if result_file:
            download_file = result_file
            # Tell UI we are done and supply the filename
            q.put(f"DONE|{result_file}")
        else:
            q.put("DONE|ERROR")
    except Exception as e:
        q.put(f"ERRO: {str(e)}")
        q.put("DONE|ERROR")

@app.route('/ping')
def ping():
    # Segurança: Verifica se o token enviado no cabeçalho ou query bate com o esperado
    secret = os.environ.get("PING_SECRET")
    token = request.headers.get("X-Ping-Token") or request.args.get("token")
    
    if secret and token != secret:
        return "Unauthorized", 401
        
    return "pong", 200

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/start_scrape', methods=['POST'])
def start_scrape():
    global download_file, status_queue, cancel_event
    data = request.json
    keyword = data.get('keyword', '')
    headless = data.get('headless', True)
    max_results = data.get('max_results', None)
    min_rating = data.get('min_rating', None)
    site_filter = data.get('site_filter', 'todos')
    
    if not keyword:
        return jsonify({"error": "A palavra-chave é obrigatória"}), 400
        
    download_file = None
    
    # Esvaziando a fila caso exista processo anterior
    while not status_queue.empty():
        try:
            status_queue.get_nowait()
        except queue.Empty:
            break
            
    # Reset cancellation flag
    cancel_event.clear()
            
    # Rodar o bot numa thread separada para não travar a API do Flask
    thread = threading.Thread(
        target=scraper_thread, 
        args=(keyword, headless, max_results, min_rating, site_filter, status_queue, cancel_event)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})
    
@app.route('/api/cancel_scrape')
def cancel_scrape():
    global cancel_event
    cancel_event.set()
    return jsonify({"status": "canceling"})

@app.route('/api/scrape_stream')
def scrape_stream():
    def event_stream():
        global status_queue
        while True:
            try:
                # Aguarda até aparecer uma mensagem na fila
                msg = status_queue.get(timeout=30)
                # Formato server-sent event
                yield f"data: {msg}\n\n"
                
                if msg.startswith("DONE|"):
                    break
            except queue.Empty:
                # Keep alive
                yield ": keep-alive\n\n"
                
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/api/download')
def download():
    global download_file
    if download_file and os.path.exists(download_file):
        return send_file(download_file, as_attachment=True)
    return "Nenhum arquivo para download", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"Iniciando o painel de prospecção do Google Maps na porta {port}!")
    app.run(host='0.0.0.0', port=port, debug=True, threaded=True)
