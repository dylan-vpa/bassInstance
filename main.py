from flask import Flask, request, jsonify, send_file
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
import requests
import pandas as pd
import os
import time
import unicodedata
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configuración
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
audios_generados = {}
ultimo_llamado = {'numero': None, 'audio_file': None}

os.makedirs('static', exist_ok=True)

def normalize(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower().strip()

def generar_audio(texto):
    try:
        headers = {'xi-api-key': ELEVENLABS_API_KEY}
        payload = {'text': texto, 'voice_settings': {'stability': 0.5, 'similarity_boost': 0.75}}
        resp = requests.post(f'https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}',
                             headers=headers, json=payload, timeout=30)
        if resp.ok:
            audio_filename = f'audio_{os.urandom(4).hex()}.mp3'
            audio_path = os.path.join('static', audio_filename)
            with open(audio_path, 'wb') as f:
                f.write(resp.content)
            print(f"✅ Audio generado: {audio_path}")
            return audio_path
        else:
            print(f"❌ Error en ElevenLabs: {resp.text}")
            return None
    except Exception as e:
        print(f"❌ Error generando audio: {str(e)}")
        return None

def consulta_ollama(prompt):
    try:
        resp = requests.post(OLLAMA_URL, json={'model': 'ana', 'prompt': prompt, 'stream': False}, timeout=30)
        if resp.ok:
            return resp.json().get('response', '')
        else:
            print(f"❌ Error consultando IA: {resp.text}")
            return 'No entendí bien, ¿puedes repetir?'
    except Exception as e:
        print(f"❌ Error consulta_ollama: {str(e)}")
        return 'No entendí bien, ¿puedes repetir?'

def enviar_whatsapp(numero, mensaje):
    try:
        payload = {'messaging_product': 'whatsapp', 'to': numero, 'type': 'text', 'text': {'body': mensaje}}
        headers = {'Authorization': f'Bearer {WHATSAPP_TOKEN}', 'Content-Type': 'application/json'}
        resp = requests.post(WHATSAPP_URL, json=payload, headers=headers)
        if not resp.ok:
            print(f"❌ Error enviando WhatsApp a {numero}: {resp.text}")
    except Exception as e:
        print(f"❌ Error enviar_whatsapp: {str(e)}")

@app.route('/sendNumbers', methods=['POST'])
def send_numbers():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No se proporcionó archivo válido'}), 400
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
            if not numero or numero.lower() == 'nan':
                continue
            mensaje = f"Hola {nombre}, ¿nos das permiso para llamarte?"
            enviar_whatsapp(numero, mensaje)
            historial.setdefault(numero, []).append({'from': 'bot', 'text': mensaje})
            enviados += 1
        print(f"✅ {enviados} mensajes enviados.")
        return jsonify({'status': f'{enviados} mensajes enviados'}), 200
    except Exception as e:
        print(f"❌ Error en send_numbers: {str(e)}")
        return jsonify({'error': str(e)}), 400

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        print(f"📥 Webhook recibido: {data}")
        for entry in data.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value', {})
                messages = value.get('messages', [])
                for message in messages:
                    numero = message['from']
                    if message['type'] == 'text':
                        mensaje = message['text']['body']
                        historial.setdefault(numero, []).append({'from': 'user', 'text': mensaje})
                        llamada_hecha = any(m.get('from') == 'call' for m in historial[numero])
                        ultimo_bot = next((m['text'].lower() for m in reversed(historial[numero]) if m['from'] == 'bot'), '')
                        if 'permiso para llamarte' in ultimo_bot and not llamada_hecha:
                            respuesta_ia = consulta_ollama("El usuario dijo sí. Inicia conversación.")
                            audio_path = generar_audio(respuesta_ia)
                            if audio_path:
                                audios_generados[numero] = {'audio_path': audio_path}
                                ultimo_llamado['numero'] = numero
                                hacer_llamada(numero)
                                historial[numero].append({'from': 'call', 'audio_file': audio_path, 'message': respuesta_ia})
                                enviar_whatsapp(numero, "¡Gracias! Te estamos llamando ahora.")
                        else:
                            respuesta = consulta_ollama(mensaje)
                            enviar_whatsapp(numero, respuesta)
                            historial[numero].append({'from': 'bot', 'text': respuesta})
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"❌ Error en webhook: {str(e)}")
        return jsonify({'error': str(e)}), 400

def hacer_llamada(numero):
    try:
        twiml_url = f"{SERVER_URL}/twiml/call"
        call = client.calls.create(to=numero, from_=TWILIO_CALLER_ID, url=twiml_url, method='GET')
        print(f"✅ Llamada iniciada a {numero}, SID: {call.sid}")
    except Exception as e:
        print(f"❌ Error haciendo llamada a {numero}: {str(e)}")

@app.route('/twiml/call', methods=['GET', 'POST'])
def twiml_call():
    response = VoiceResponse()
    try:
        numero = ultimo_llamado.get('numero')
        audio_info = audios_generados.get(numero)
        if audio_info and os.path.exists(audio_info['audio_path']):
            audio_url = f"{SERVER_URL}/audio/{os.path.basename(audio_info['audio_path'])}"
            response.play(audio_url)
        else:
            response.say("Hola, soy Ana, ¿en qué puedo ayudarte?")
        response.hangup()
    except Exception as e:
        print(f"❌ Error en twiml_call: {str(e)}")
        response.say("Ocurrió un error en el sistema.")
        response.hangup()
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/audio/<filename>', methods=['GET'])
def serve_audio(filename):
    file_path = os.path.join('static', filename)
    if os.path.exists(file_path):
        return send_file(file_path, mimetype='audio/mpeg')
    return jsonify({'error': 'Archivo no encontrado'}), 404

@app.route('/history/<numero>', methods=['GET'])
def get_history(numero):
    return jsonify(historial.get(numero, []))

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'API funcionando correctamente'})

if __name__ == '__main__':
    print("🚀 Iniciando API...")
    app.run(host='0.0.0.0', port=4000, debug=True)
