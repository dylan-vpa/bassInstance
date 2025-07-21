from flask import Flask, request, jsonify
from twilio.rest import Client
import requests
import pandas as pd
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# Configuración desde .env
WHATSAPP_TOKEN = os.getenv('WHATSAPP_TOKEN')
WHATSAPP_URL = os.getenv('WHATSAPP_URL')
OLLAMA_URL = os.getenv('OLLAMA_URL')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_CALLER_ID = os.getenv('TWILIO_CALLER_ID')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
historial = {}  # Guardar mensajes (en memoria; para producción usar DB)

# ---------- Recibir mensajes ----------
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    numero = data['from']
    mensaje = data['text']['body']
    historial.setdefault(numero, []).append({'from': 'user', 'text': mensaje})

    if 'IA' in mensaje.lower() or 'ollama' in mensaje.lower():
        respuesta = consulta_ollama(mensaje)
        enviar_whatsapp(numero, respuesta)
        historial[numero].append({'from': 'bot', 'text': respuesta})

    return jsonify({'status': 'ok'}), 200

# ---------- Enviar mensaje por WhatsApp ----------
def enviar_whatsapp(numero, mensaje):
    payload = {
        'messaging_product': 'whatsapp',
        'to': numero,
        'type': 'text',
        'text': {'body': mensaje}
    }
    headers = {'Authorization': f'Bearer {WHATSAPP_TOKEN}'}
    resp = requests.post(WHATSAPP_URL, json=payload, headers=headers)
    if not resp.ok:
        print(f"Error enviando mensaje a {numero}: {resp.text}")

# ---------- Consultar Ollama ----------
def consulta_ollama(prompt):
    resp = requests.post(OLLAMA_URL, json={'model': 'llama3', 'prompt': prompt})
    return resp.json().get('response', 'No entendí.')

# ---------- Subir Excel y pedir permiso ----------
@app.route('/sendNumbers', methods=['POST'])
def send_numbers():
    file = request.files['file']
    df = pd.read_excel(file)
    for _, row in df.iterrows():
        nombre = row['nombre']
        numero = str(row['número'])
        mensaje = f"Hola {nombre}, ¿nos das permiso para llamarte?"
        enviar_whatsapp(numero, mensaje)
    return jsonify({'status': 'mensajes enviados'}), 200

# ---------- Procesar respuesta de permiso ----------
@app.route('/permission_response', methods=['POST'])
def permission_response():
    data = request.json
    numero = data['from']
    mensaje = data['text']['body'].lower()
    if mensaje in ['sí', 'si', 'okay', 'ok']:
        hacer_llamada(numero)
    return jsonify({'status': 'respuesta procesada'}), 200

# ---------- Hacer llamada usando Twilio y ElevenLabs ----------
def hacer_llamada(numero):
    texto = "Hola, soy la asistente virtual. ¿Cómo puedo ayudarte?"
    audio_url = generar_audio_elevenlabs(texto)
    
    # Aquí Twilio espera un TwiML o audio público; debes tener un endpoint para servirlo
    twiml_url = f"https://tu-servidor.com/twiml/{os.path.basename(audio_url)}"
    call = client.calls.create(
        to=numero,
        from_=TWILIO_CALLER_ID,
        url=twiml_url
    )
    historial.setdefault(numero, []).append({'from': 'call', 'sid': call.sid})

# ---------- Generar audio con ElevenLabs ----------
def generar_audio_elevenlabs(texto):
    headers = {'xi-api-key': ELEVENLABS_API_KEY}
    response = requests.post(
        'https://api.elevenlabs.io/v1/text-to-speech/VOICE_ID',
        headers=headers,
        json={'text': texto, 'voice_settings': {'stability': 0.5, 'similarity_boost': 0.75}}
    )
    audio_path = f'static/audio_{os.urandom(4).hex()}.mp3'
    with open(audio_path, 'wb') as f:
        f.write(response.content)
    return f'https://tu-servidor.com/{audio_path}'

# ---------- Consultar historial ----------
@app.route('/history/<numero>', methods=['GET'])
def get_history(numero):
    return jsonify(historial.get(numero, []))

if __name__ == '__main__':
    app.run(port=5000, debug=True)
