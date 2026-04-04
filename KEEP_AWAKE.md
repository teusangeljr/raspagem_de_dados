# 🚀 Mantendo sua Aplicação Ativa no Render

O plano gratuito do Render coloca o servidor para "dormir" após 15 minutos de inatividade. Para evitar isso e garantir que sua aplicação esteja sempre pronta (sem o atraso de 1 minuto ao abrir), siga os passos abaixo:

## Método Recomendado: Cron-Job.org (Gratuito)

O `cron-job.org` é um serviço gratuito que pode fazer uma requisição para sua aplicação em intervalos regulares, impedindo-a de hibernar.

### Passo a Passo:

1.  Acesse [cron-job.org](https://cron-job.org/) e crie uma conta gratuita.
2.  No painel, clique em **"Create Cronjob"**.
3.  **Title:** `Wake up Raspagem Maps` (ou qualquer nome).
4.  **URL:** `https://raspagem-lcqn.onrender.com/ping`
5.  **Method:** GET (padrão).
6.  **Adicionar Segurança:** Na aba **"HTTP Headers"** do Cron-Job:
    *   No campo **Key**, coloque: `X-Ping-Token`
    *   No campo **Value**, coloque sua senha secreta (definida no Render - veja abaixo).
7.  **Execution Schedule:** Selecione **"Every 14 minutes"**.
8.  Clique em **"Create"**.

---

## 🔒 Como configurar a "Senha Secreta" no Render (Segurança)

Para que apenas o seu "cron" consiga dar o ping na sua máquina:

1.  Acesse o painel do seu serviço no **Render**.
2.  Vá em **Environment**.
3.  Adicione uma nova variável:
    *   **Key:** `PING_SECRET`
    *   **Value:** `angel` (Senha que definimos agora!)
4.  Dê o "Save Changes".
5.  No Cron-Job.org, o `Value` que você colocar no cabeçalho `X-Ping-Token` deve ser i-gu-al a esse `PING_SECRET`.

---

## Por que não usar um Cron interno (no Python)?

Se tentarmos rodar um thread de "ping" dentro do próprio código, ela parará de funcionar assim que o Render congelar os processos do container após os 15 minutos de inatividade. Por isso, um **agente externo** (como o Cron-Job.org ou UptimeRobot) é necessário para "dar o choque" inicial e manter a máquina ligada.

---

## Benefícios das Otimizações Aplicadas:
- **Sem atraso de 1 minuto:** A aplicação estará sempre "quente".
- **Melhor detecção de porta:** O Render agora identifica o serviço mais rápido após o deploy.
- **Scraping mais Veloz:** Reduzimos os tempos de espera inertes no script de extração.
