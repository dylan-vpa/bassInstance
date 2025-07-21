from flask import Flask, request, jsonify, send_file
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
import requests
import pandas as pd
import os
import unicodedata
from dotenv import load_dotenv

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

def normalize(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower().strip()

def generar_audio(texto):
    try:
        headers = {'xi-api-key': ELEVENLABS_API_KEY}
        payload = {'text': texto, 'voice_settings': {'stability': 0.5, 'similarity_boost': 0.75}}
        resp = requests.post(
            f'https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}',
            headers=headers, json=payload, timeout=30
        )
        if resp.ok:
            audio_filename = f'audio_{os.urandom(4).hex()}.mp3'
            audio_path = os.path.join('static', audio_filename)
            with open(audio_path, 'wb') as f:
                f.write(resp.content)
            print(f"✅ Audio generado: {audio_path}")
            return audio_path
        else:
            print(f"❌ ElevenLabs error: {resp.text}")
            return None
    except Exception as e:
        print(f"❌ Audio error: {str(e)}")
        return None

def consulta_ollama(prompt):
    try:
        resp = requests.post(OLLAMA_URL, json={'model': 'ana', 'prompt': prompt, 'stream': False}, timeout=30)
        if resp.ok:
            respuesta = resp.json().get('response', '')
            return respuesta
        else:
            print(f"❌ Ollama error: {resp.text}")
            return 'No entendí bien, ¿puedes repetir?'
    except Exception as e:
        print(f"❌ Ollama error: {str(e)}")
        return 'No entendí bien, ¿puedes repetir?'

def enviar_whatsapp(numero, mensaje):
    try:
        payload = {'messaging_product': 'whatsapp', 'to': numero, 'type': 'text', 'text': {'body': mensaje}}
        headers = {'Authorization': f'Bearer {WHATSAPP_TOKEN}', 'Content-Type': 'application/json'}
        resp = requests.post(WHATSAPP_URL, json=payload, headers=headers)
        if not resp.ok:
            print(f"❌ Error enviando WhatsApp a {numero}: {resp.text}")
    except Exception as e:
        print(f"❌ WhatsApp error: {str(e)}")

@app.route('/sendNumbers', methods=['POST'])
def send_numbers():
    try:
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
                mensaje = f"Hola {nombre}, ¿nos das permiso para llamarte?"
                print(f"[WHATSAPP-BOT] {numero}: {mensaje}")
                enviar_whatsapp(numero, mensaje)
                enviados += 1
        return jsonify({'status': f'{enviados} mensajes enviados'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    for entry in data.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            messages = value.get('messages', [])
            for message in messages:
                numero = message['from']
                if message['type'] == 'text':
                    texto_usuario = message['text']['body']
                    print(f"[WHATSAPP-USUARIO] {numero}: {texto_usuario}")
                    ultimo_llamado['numero'] = numero
                    respuesta = consulta_ollama("El usuario dijo sí. Inicia conversación.")
                    print(f"[WHATSAPP-BOT] {numero}: {respuesta}")
                    audio_path = generar_audio(respuesta)
                    if audio_path:
                        hacer_llamada(numero)
    return jsonify({'status': 'ok'}), 200

def hacer_llamada(numero):
    twiml_url = f"{SERVER_URL}/twiml/call"
    client.calls.create(to=numero, from_=TWILIO_CALLER_ID, url=twiml_url, method='POST')

@app.route('/twiml/call', methods=['POST'])
def twiml_call():
    response = VoiceResponse()
    gather = Gather(
        input='speech',
        action='/twiml/response',
        method='POST',
        timeout=5,
        speechTimeout='auto',
        language='es-CO'  # Español Colombia para mejor reconocimiento
    )
    numero = ultimo_llamado.get('numero')
    saludo = "Hola, soy Ana. ¿Cómo puedo ayudarte?"
    print(f"[LLAMADA-BOT] {saludo}")
    audio_path = generar_audio(saludo)
    if audio_path:
        audio_url = f"{SERVER_URL}/audio/{os.path.basename(audio_path)}"
        gather.play(audio_url)
    else:
        gather.say(saludo, language='es-CO')
    response.append(gather)
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/twiml/response', methods=['POST'])
def twiml_response():
    response = VoiceResponse()
    user_input = request.form.get('SpeechResult')
    print(f"[LLAMADA-USUARIO RAW] {user_input}")

    if user_input and user_input.strip() != '':
        respuesta = consulta_ollama(user_input)
        print(f"[LLAMADA-BOT] {respuesta}")
        audio_path = generar_audio(respuesta)
        gather = Gather(
            input='speech',
            action='/twiml/response',
            method='POST',
            timeout=5,
            speechTimeout='auto',
            language='es-CO'
        )
        if audio_path:
            audio_url = f"{SERVER_URL}/audio/{os.path.basename(audio_path)}"
            gather.play(audio_url)
        else:
            gather.say(respuesta, language='es-CO')
        response.append(gather)
    else:
        print("[LLAMADA] No se reconoció audio, repitiendo pregunta")
        response.say("No escuché nada. ¿Puedes repetir, por favor?", language='es-CO')
        response.redirect('/twiml/call')
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/audio/<filename>', methods=['GET'])
def serve_audio(filename):
    file_path = os.path.join('static', filename)
    if os.path.exists(file_path):
        return send_file(file_path, mimetype='audio/mpeg')
    return jsonify({'error': 'Archivo no encontrado'}), 404

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    print("🚀 Iniciando API...")
    app.run(host='0.0.0.0', port=4000, debug=True)
