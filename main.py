from flask import Flask, request, jsonify, send_file
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
import requests, pandas as pd, os, unicodedata, threading, time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import re

load_dotenv()
app = Flask(__name__)

WHATSAPP_TOKEN = os.getenv('WHATSAPP_TOKEN')
WHATSAPP_URL = os.getenv('WHATSAPP_URL')
OLLAMA_URL = os.getenv('OLLAMA_URL')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_CALLER_ID = os.getenv('TWILIO_CALLER_ID')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
ELEVENLABS_VOICE_ID = os.getenv('ELEVENLABS_VOICE_ID')
SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:4000')

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
historial = {}
ultimo_llamado = {'numero': None}
os.makedirs('static', exist_ok=True)

# NUEVO: seguimiento por número
seguimiento = {}

def normalize(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower().strip()

def generar_audio(texto):
    headers = {'xi-api-key': ELEVENLABS_API_KEY}
    payload = {'text': texto, 'voice_settings': {'stability': 0.5, 'similarity_boost': 0.75}}
    resp = requests.post(f'https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}', headers=headers, json=payload, timeout=30)
    if resp.ok:
        audio_filename = f'audio_{os.urandom(4).hex()}.mp3'
        audio_path = os.path.join('static', audio_filename)
        with open(audio_path, 'wb') as f:
            f.write(resp.content)
        return audio_path
    return None

def consulta_ollama(prompt):
    resp = requests.post(OLLAMA_URL, json={'model': 'ana', 'prompt': prompt, 'stream': False}, timeout=30)
    if resp.ok:
        respuesta = resp.json().get('response', '')
        respuesta = re.sub(r'<think>.*?</think>', '', respuesta, flags=re.DOTALL).strip()
        return respuesta
    return 'No entendí bien, ¿puedes repetir?'

def enviar_whatsapp(numero, mensaje):
    payload = {'messaging_product': 'whatsapp', 'to': numero, 'type': 'text', 'text': {'body': mensaje}}
    headers = {'Authorization': f'Bearer {WHATSAPP_TOKEN}', 'Content-Type': 'application/json'}
    requests.post(WHATSAPP_URL, json=payload, headers=headers)

def hacer_llamada(numero):
    twiml_url = f"{SERVER_URL}/twiml/call"
    client.calls.create(to=numero, from_=TWILIO_CALLER_ID, url=twiml_url, method='POST')
    print(f"[Llamada-Iniciada] Llamando a {numero}")

@app.route('/sendNumbers', methods=['POST'])
def send_numbers():
    file = request.files['file']
    df = pd.read_excel(file)
    normalized_cols = [normalize(c) for c in df.columns]
    col_map = {normalize(c): c for c in df.columns}
    if 'nombre' not in normalized_cols or 'numero' not in normalized_cols:
        return jsonify({'error': 'El Excel debe tener columnas nombre y número'}), 400
    enviados = 0
    for _, row in df.iterrows():
        nombre = str(row[col_map['nombre']]).strip()
        numero = str(row[col_map['numero']]).strip()
        if numero.lower() != 'nan':
            mensaje = f"¡Hola {nombre}! Soy Ana de AVANZA 👋. Te contacto porque tenemos condiciones financieras muy especiales para empleados públicos como tú. Tasas desde 1.6% mensual y montos hasta 150 millones 💰. ¿Te interesaría recibir una llamada para conocer más detalles?"
            enviar_whatsapp(numero, mensaje)
            historial[numero] = [f"IA: {mensaje}"]
            seguimiento[numero] = {
                'nombre': nombre,
                'mensajes_enviados': 1,
                'ultimo_mensaje': datetime.now(),
                'llamadas_realizadas': 1,  # Marcamos 1 porque haremos la llamada ya
                'ultima_llamada': datetime.now(),
                'responde': False
            }
            ultimo_llamado['numero'] = numero  # Seteamos último para el flujo de voz
            hacer_llamada(numero)  # <<<<< HACEMOS LA LLAMADA DIRECTAMENTE
            print(f"[WhatsApp-BOT] {numero}: {mensaje}")
            enviados += 1
    return jsonify({'status': f'{enviados} mensajes enviados y llamadas iniciadas'}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    for entry in data.get('entry', []):
        for change in entry.get('changes', []):
            messages = change.get('value', {}).get('messages', [])
            for message in messages:
                numero = message['from']
                if message['type'] == 'text':
                    texto_usuario = message['text']['body'].strip()
                    historial.setdefault(numero, [])
                    historial[numero].append(f"Usuario: {texto_usuario}")
                    seguimiento.setdefault(numero, {'responde': False}).update({'responde': True})
                    print(f"[WhatsApp-Usuario] {numero}: {texto_usuario}")

                    conversacion = '\n'.join(historial[numero])
                    respuesta = consulta_ollama(conversacion)
                    enviar_whatsapp(numero, respuesta)
                    historial[numero].append(f"IA: {respuesta}")
                    print(f"[WhatsApp-BOT Chat] {numero}: {respuesta}")
    return jsonify({'status': 'ok'}), 200

@app.route('/twiml/call', methods=['POST'])
def twiml_call():
    response = VoiceResponse()
    gather = Gather(input='speech', action='/twiml/response', method='POST', timeout=5, speechTimeout='auto', language='es-CO')
    saludo = "Hola, soy Ana. ¿Cómo puedo ayudarte?"
    audio_path = generar_audio(saludo)
    if audio_path:
        gather.play(f"{SERVER_URL}/audio/{os.path.basename(audio_path)}")
    else:
        gather.say(saludo, language='es-CO')
    response.append(gather)
    print(f"[Llamada-BOT] Ana: {saludo}")
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/twiml/response', methods=['POST'])
def twiml_response():
    response = VoiceResponse()
    user_input = request.form.get('SpeechResult')
    numero = ultimo_llamado.get('numero')

    if user_input and user_input.strip() and numero:
        print(f"[Llamada-Usuario] Dijo: {user_input}")
        historial.setdefault(numero, []).append(f"Usuario: {user_input}")

        conversacion = '\n'.join(historial[numero])
        respuesta = consulta_ollama(conversacion)
        historial[numero].append(f"IA: {respuesta}")

        gather = Gather(input='speech', action='/twiml/response', method='POST', timeout=5, speechTimeout='auto', language='es-CO')
        audio_path = generar_audio(respuesta)
        if audio_path:
            gather.play(f"{SERVER_URL}/audio/{os.path.basename(audio_path)}")
        else:
            gather.say(respuesta, language='es-CO')
        response.append(gather)
        print(f"[Llamada-BOT] Ana: {respuesta}")
    else:
        response.say("No escuché nada. ¿Puedes repetir por favor?", language='es-CO')
        response.redirect('/twiml/call')
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/audio/<filename>', methods=['GET'])
def serve_audio(filename):
    path = os.path.join('static', filename)
    return send_file(path, mimetype='audio/mpeg') if os.path.exists(path) else ('', 404)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'})

@app.route('/estado', methods=['GET'])
def estado():
    estados = {}
    for numero, conversaciones in historial.items():
        chat = '\n'.join(conversaciones)
        resumen = consulta_ollama(f"Resume la conversación y da un estado general en pocas palabras:\n{chat}")
        estados[numero] = resumen
    return jsonify(estados)

if __name__ == '__main__':
    # threading.Thread(target=enviar_mensajes_programados, daemon=True).start()  # <<< COMENTADO para desactivar automático
    app.run(host='0.0.0.0', port=4000, debug=True)
