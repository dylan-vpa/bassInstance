from flask import Flask, request, jsonify, send_file
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
import requests
import pandas as pd
import os
import time
from dotenv import load_dotenv
import unicodedata

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

os.makedirs('static', exist_ok=True)

def normalize(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower().strip()

def generar_audio_elevenlabs(texto):
    try:
        headers = {'xi-api-key': ELEVENLABS_API_KEY, 'Content-Type': 'application/json'}
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
        print(f"❌ ElevenLabs error: {resp.text}")
        return None
    except Exception as e:
        print(f"❌ Error generando audio: {str(e)}")
        return None

def generar_audio_respuesta(numero, texto_usuario):
    respuesta_ia = consulta_ollama(f"El usuario dijo: {texto_usuario}. Responde breve y amigable.")
    audio_path = generar_audio_elevenlabs(respuesta_ia)
    if audio_path:
        audio_url = f"{SERVER_URL}/audio/{os.path.basename(audio_path)}"
        audios_generados[numero] = {'audio_path': audio_path, 'audio_url': audio_url, 'mensaje': respuesta_ia}
        return True
    return False

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
                        llamada_ya_hecha = any(m.get('from') == 'call' for m in historial[numero])
                        ultimo_mensaje_bot = next((m['text'].lower() for m in reversed(historial[numero]) if m['from'] == 'bot'), '')
                        if 'permiso para llamarte' in ultimo_mensaje_bot and not llamada_ya_hecha:
                            if generar_audio_respuesta(numero, mensaje):
                                hacer_llamada(numero)
                                enviar_whatsapp(numero, "¡Gracias! Te estamos llamando ahora.")
                                historial[numero].append({'from': 'call', 'audio_file': audios_generados[numero]['audio_path'], 'message': audios_generados[numero]['mensaje']})
                            else:
                                enviar_whatsapp(numero, "No pudimos generar la llamada, intenta más tarde.")
                        else:
                            respuesta = consulta_ollama(mensaje)
                            if respuesta:
                                enviar_whatsapp(numero, respuesta)
                                historial[numero].append({'from': 'bot', 'text': respuesta})
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"❌ Error en webhook: {str(e)}")
        return jsonify({'error': str(e)}), 400

def enviar_whatsapp(numero, mensaje):
    payload = {'messaging_product': 'whatsapp', 'to': numero, 'type': 'text', 'text': {'body': mensaje}}
    headers = {'Authorization': f'Bearer {WHATSAPP_TOKEN}', 'Content-Type': 'application/json'}
    try:
        resp = requests.post(WHATSAPP_URL, json=payload, headers=headers)
        if not resp.ok:
            print(f"❌ Error enviando WhatsApp a {numero}: {resp.text}")
    except Exception as e:
        print(f"❌ Error en enviar_whatsapp: {str(e)}")

def consulta_ollama(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            resp = requests.post(OLLAMA_URL, json={'model': 'ana', 'prompt': prompt, 'stream': False}, timeout=30)
            if resp.ok:
                return resp.json().get('response', '')
            print(f"❌ Ollama error intento {attempt +1}: {resp.text}")
        except Exception as e:
            print(f"❌ Error en consulta_ollama intento {attempt +1}: {str(e)}")
        time.sleep(1)
    return 'Hola, gracias por contestar.'

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

def hacer_llamada(numero):
    try:
        twiml_url = f"{SERVER_URL}/twiml/call"
        call = client.calls.create(to=numero, from_=TWILIO_CALLER_ID, url=twiml_url, method='GET')
        print(f"✅ Llamada iniciada a {numero}, SID: {call.sid}")
    except Exception as e:
        print(f"❌ Error haciendo llamada a {numero}: {str(e)}")

@app.route('/twiml/call', methods=['GET'])
def twiml_call():
    response = VoiceResponse()
    try:
        if audios_generados:
            # Tomamos el último número agregado
            ultimo_numero = list(audios_generados.keys())[-1]
            audio_info = audios_generados.get(ultimo_numero)
            if audio_info and os.path.exists(audio_info['audio_path']):
                response.play(audio_info['audio_url'])
            else:
                response.say("Lo siento, no tengo un mensaje para ti ahora.")
        else:
            response.say("Lo siento, no tengo un mensaje para ti ahora.")
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
