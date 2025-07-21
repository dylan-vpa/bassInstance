from flask import Flask, request, jsonify, send_file
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
import requests
import os
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configuración
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_CALLER_ID = os.getenv('TWILIO_CALLER_ID')
SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:4000')
OLLAMA_URL = os.getenv('OLLAMA_URL')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
ELEVENLABS_VOICE_ID = os.getenv('ELEVENLABS_VOICE_ID')

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
conversations = {}

# ==================== FUNCIONES ====================

def consulta_ollama(prompt):
    try:
        resp = requests.post(OLLAMA_URL, json={'model': 'ana', 'prompt': prompt, 'stream': False}, timeout=30)
        if resp.ok:
            return resp.json().get('response', 'Lo siento, no entendí.')
        else:
            print(f"Ollama error: {resp.text}")
    except Exception as e:
        print(f"Ollama exception: {str(e)}")
    return 'Lo siento, no entendí.'

def generar_audio(texto):
    try:
        headers = {'xi-api-key': ELEVENLABS_API_KEY}
        payload = {'text': texto, 'voice_settings': {'stability': 0.5, 'similarity_boost': 0.75}}
        resp = requests.post(f'https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}', headers=headers, json=payload, timeout=30)
        if resp.ok:
            audio_filename = f'audio_{time.time()}.mp3'
            audio_path = os.path.join('static', audio_filename)
            with open(audio_path, 'wb') as f:
                f.write(resp.content)
            return f"{SERVER_URL}/audio/{audio_filename}"
        else:
            print(f"ElevenLabs error: {resp.text}")
    except Exception as e:
        print(f"ElevenLabs exception: {str(e)}")
    return None

# ==================== ENDPOINT DE LLAMADA INICIAL ====================

@app.route('/twiml/call', methods=['POST', 'GET'])
def twiml_call():
    numero = request.values.get('From', 'unknown')
    response = VoiceResponse()
    saludo = "Hola, soy Ana, tu asistente virtual. ¿En qué puedo ayudarte?"

    # Guardar conversación inicial
    conversations[numero] = []

    gather = Gather(input='speech', action='/twiml/continue', method='POST', timeout=5)
    gather.say(saludo, language='es-ES')
    response.append(gather)

    response.say("No escuché nada. Adiós.")
    response.hangup()
    return str(response), 200, {'Content-Type': 'text/xml'}

# ==================== ENDPOINT DE CONTINUIDAD ====================

@app.route('/twiml/continue', methods=['POST'])
def twiml_continue():
    numero = request.values.get('From', 'unknown')
    speech_result = request.values.get('SpeechResult', '')
    response = VoiceResponse()

    print(f"Usuario {numero} dijo: {speech_result}")
    conversations.setdefault(numero, []).append({'from': 'user', 'text': speech_result})

    respuesta_ia = consulta_ollama(speech_result)
    conversations[numero].append({'from': 'bot', 'text': respuesta_ia})

    audio_url = generar_audio(respuesta_ia)
    if not audio_url:
        response.say("Lo siento, hubo un error generando la respuesta. Adiós.")
        response.hangup()
        return str(response), 200, {'Content-Type': 'text/xml'}

    gather = Gather(input='speech', action='/twiml/continue', method='POST', timeout=5)
    gather.play(audio_url)
    response.append(gather)

    response.say("No escuché nada. Adiós.")
    response.hangup()
    return str(response), 200, {'Content-Type': 'text/xml'}

# ==================== SERVIR AUDIOS ====================

@app.route('/audio/<filename>', methods=['GET'])
def serve_audio(filename):
    audio_path = os.path.join('static', filename)
    if os.path.exists(audio_path):
        return send_file(audio_path, mimetype='audio/mpeg')
    else:
        return jsonify({'error': 'Audio no encontrado'}), 404

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

# ==================== MAIN ====================

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    print("🚀 API corriendo en puerto 4000")
    app.run(host='0.0.0.0', port=4000, debug=True)
