document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('scrape-form');
    const keywordInput = document.getElementById('keyword');
    const headlessToggle = document.getElementById('headless');
    const maxQtyInput = document.getElementById('max-qty');
    const minRatingInput = document.getElementById('min-rating');
    const siteFilterInput = document.getElementById('site-filter');
    const submitBtn = document.getElementById('submit-btn');
    const cancelBtn = document.getElementById('cancel-btn');
    const btnText = document.querySelector('.btn-text');
    const loaderWrapper = document.querySelector('.loader-spinner');
    const logOutput = document.getElementById('log-output');
    const resultsArea = document.getElementById('results-area');
    
    let eventSource = null;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const keyword = keywordInput.value.trim();
        if (!keyword) return;

        // Reset UI states
        startLoading();
        clearLogs();
        resultsArea.classList.add('hidden');
        appendLog(`Iniciando processo para prospectar: "${keyword}"`, 'highlight-msg');

        try {
            // Trigger the backend process
            const response = await fetch('/api/start_scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    keyword: keyword,
                    headless: headlessToggle.checked,
                    max_results: maxQtyInput.value ? parseInt(maxQtyInput.value) : null,
                    min_rating: minRatingInput.value ? parseFloat(minRatingInput.value) : null,
                    site_filter: siteFilterInput.value
                })
            });

            const data = await response.json();
            
            if (response.ok) {
                // Initialize the event stream to listen to python logs
                setupEventStream();
            } else {
                appendLog(`Erro: ${data.error || 'Falha ao iniciar processo'}`, 'error-msg');
                stopLoading();
            }
        } catch (error) {
            appendLog(`Erro de conexão com o servidor.`, 'error-msg');
            stopLoading();
        }
    });

    cancelBtn.addEventListener('click', async () => {
        appendLog(`Solicitando cancelamento do processo...`, 'highlight-msg');
        cancelBtn.disabled = true;
        cancelBtn.querySelector('.btn-text').textContent = "Cancelando...";
        
        try {
            await fetch('/api/cancel_scrape');
        } catch (error) {
            appendLog(`Erro ao enviar sinal de cancelamento.`, 'error-msg');
        }
    });

    function setupEventStream() {
        if (eventSource) {
            eventSource.close();
        }
        
        eventSource = new EventSource('/api/scrape_stream');
        
        eventSource.onmessage = function(event) {
            const msg = event.data;
            
            // Check if process finished
            if (msg.startsWith("DONE|")) {
                eventSource.close();
                stopLoading();
                
                const returnData = msg.split("DONE|")[1];
                if (returnData === "ERROR") {
                    appendLog("O processo foi finalizado com erro ou interrompido.", "error-msg");
                } else if (returnData === "CANCELED") {
                    appendLog("Processo interrompido pelo usuário antecipadamente.", "error-msg");
                } else {
                    appendLog("Extração completa com sucesso!", "success-msg");
                    showDownload(returnData);
                }
                return;
            }
            
            // Standard log message handling
            if (msg.includes("erro") || msg.includes("Erro") || msg.includes("ERRO")) {
                appendLog(msg, "error-msg");
            } else if (msg.includes("SUCESSO") || msg.includes("concluído")) {
                appendLog(msg, "success-msg");
            } else {
                appendLog(msg);
            }
        };

        eventSource.onerror = function(err) {
            console.error("SSE Error:", err);
            // Ignore minor reconnect errors, close if it becomes persistent.
        };
    }

    function appendLog(message, className = '') {
        const div = document.createElement('div');
        div.className = `log-entry ${className}`;
        
        // Formatar o timestamp para exibir junto ao evento
        const now = new Date();
        const time = now.toLocaleTimeString('pt-BR', {hour12: false});
        div.innerHTML = `<span style="color: #64748b;">[${time}]</span> ${message}`;
        
        logOutput.appendChild(div);
        
        // Auto-scroll
        logOutput.scrollTop = logOutput.scrollHeight;
    }

    function clearLogs() {
        logOutput.innerHTML = '';
    }

    function startLoading() {
        submitBtn.style.display = 'none';
        cancelBtn.style.display = 'block';
        cancelBtn.disabled = false;
        cancelBtn.querySelector('.btn-text').textContent = "Cancelar (Parar)";
        loaderWrapper.style.display = 'block';
        keywordInput.disabled = true;
        headlessToggle.disabled = true;
        maxQtyInput.disabled = true;
        minRatingInput.disabled = true;
        siteFilterInput.disabled = true;
    }

    function stopLoading() {
        submitBtn.style.display = 'block';
        cancelBtn.style.display = 'none';
        btnText.textContent = "Iniciar Extração Mágica";
        loaderWrapper.style.display = 'none';
        keywordInput.disabled = false;
        headlessToggle.disabled = false;
        maxQtyInput.disabled = false;
        minRatingInput.disabled = false;
        siteFilterInput.disabled = false;
    }
    
    function showDownload(filename) {
        resultsArea.classList.remove('hidden');
    }
});
