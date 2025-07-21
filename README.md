# WhatsApp Chat API + IA (Ollama) + Llamadas Twilio + ElevenLabs

Este proyecto permite:
✅ Recibir/enviar mensajes de WhatsApp Business  
✅ Integrarse con IA (Ollama)  
✅ Enviar archivos Excel con números para pedir permiso de llamada  
✅ Hacer llamadas automáticas con Twilio y voz generada con ElevenLabs

---

## 🔧 Configuración

### 1️⃣ WhatsApp Business API (Meta)

1. Ve a [Meta for Developers](https://developers.facebook.com/)  
2. Crea una app tipo **WhatsApp Business**  
3. Consigue:
   - `WHATSAPP_TOKEN` (Access Token)
   - `WHATSAPP_URL` → formato: `https://graph.facebook.com/v19.0/TU_NUMERO_ID/messages`

Configura el webhook para recibir mensajes:
- URL: `https://TU_DOMINIO/webhook`
- Eventos: mensajes, mensajes entregados

---

### 2️⃣ Twilio

1. Crea cuenta en [Twilio](https://www.twilio.com/)  
2. Consigue:
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - Número verificado (`TWILIO_CALLER_ID`)

Configura:
- En la consola Twilio, asigna el **Webhook de llamada** a:
  `https://TU_DOMINIO/twiml/AUDIO_GENERADO`

---

### 3️⃣ ElevenLabs

1. Crea cuenta en [ElevenLabs](https://elevenlabs.io/)  
2. Consigue:
   - `ELEVENLABS_API_KEY`

Identifica un `VOICE_ID` válido (lo puedes ver en su panel).  
Actualiza en `app.py` donde dice `'VOICE_ID'`.

---

### 4️⃣ Ollama (IA local)

- Instala Ollama en tu servidor: https://ollama.com/download  
- Levanta modelo:
  ```bash
  ollama serve
  ollama pull llama3

⚙️ Variables de entorno (.env)

Crea archivo .env en la raíz:

WHATSAPP_TOKEN=tu_token_whatsapp_business
WHATSAPP_URL=https://graph.facebook.com/v19.0/TU_NUMERO_ID/messages
OLLAMA_URL=http://localhost:11434/api/generate
TWILIO_ACCOUNT_SID=tu_account_sid
TWILIO_AUTH_TOKEN=tu_auth_token
TWILIO_CALLER_ID=tu_numero_twilio
ELEVENLABS_API_KEY=tu_api_key_elevenlabs

🚀 Cómo levantar

    Clona el repo:

git clone TU_REPO
cd TU_REPO

Corre:

    ./run_api.sh

La API quedará expuesta en http://0.0.0.0:4000
⚠️ Producción (importante)

✅ Usa un servidor público con HTTPS (ej. Nginx + Certbot)
✅ Expone los audios generados en un endpoint público (ej. /static/)
✅ Usa base de datos real (ej. Postgres o SQLite) en lugar de historial en memoria
✅ Considera usar Gunicorn + Nginx para producción (en vez de Flask dev server)
🛠 Herramientas recomendadas

    Docker + Docker Compose → para aislar servicios

    ngrok → para pruebas rápidas de webhook

    Supervisord o systemd → para levantar en background
