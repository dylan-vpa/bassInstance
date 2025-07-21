from flask import Flask, request, jsonify, send_file
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
import requests
import pandas as pd
import os
from dotenv import load_dotenv

# Cargar variables de entorno (.env)
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
SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:4000')  # URL pública de tu servidor

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
historial = {}  # Historial en memoria

# --------- Verificación y recepción de mensajes de WhatsApp ----------
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        hub_mode = request.args.get('hub.mode')
        hub_challenge = request.args.get('hub.challenge')
        hub_verify_token = request.args.get('hub.verify_token')
        
        if hub_mode == 'subscribe' and hub_verify_token == os.getenv('WHATSAPP_VERIFY_TOKEN'):
            print(f"✅ Webhook verificado correctamente. Challenge: {hub_challenge}")
            return hub_challenge
        else:
            print(f"❌ Token de verificación incorrecto. Esperado: {os.getenv('WHATSAPP_VERIFY_TOKEN')}, Recibido: {hub_verify_token}")
            return 'Forbidden', 403

    elif request.method == 'POST':
        try:
            data = request.json
            print(f"Webhook recibido: {data}")
            
            if 'entry' in data and data['entry']:
                entry = data['entry'][0]
                if 'changes' in entry and entry['changes']:
                    change = entry['changes'][0]
                    if 'value' in change and 'messages' in change['value']:
                        messages = change['value']['messages']
                        for message in messages:
                            numero = message['from']
                            if message['type'] == 'text':
                                mensaje = message['text']['body']
                                
                                # Guardar en historial
                                historial.setdefault(numero, []).append({'from': 'user', 'text': mensaje})
                                
                                mensaje_lower = mensaje.lower()
                                if any(word in mensaje_lower for word in ['sí', 'si', 'okay', 'ok', 'yes']):
                                    hacer_llamada(numero)
                                    respuesta = "¡Gracias! Te estamos llamando ahora."
                                else:
                                    respuesta = consulta_ollama(mensaje)
                                
                                enviar_whatsapp(numero, respuesta)
                                historial[numero].append({'from': 'bot', 'text': respuesta})
            
            return jsonify({'status': 'ok'}), 200
        except Exception as e:
            print(f"Error en webhook: {str(e)}")
            return jsonify({'error': str(e)}), 400

# --------- Enviar mensaje por WhatsApp ----------
def enviar_whatsapp(numero, mensaje):
    try:
        payload = {
            'messaging_product': 'whatsapp',
            'to': numero,
            'type': 'text',
            'text': {'body': mensaje}
        }
        headers = {
            'Authorization': f'Bearer {WHATSAPP_TOKEN}',
            'Content-Type': 'application/json'
        }
        resp = requests.post(WHATSAPP_URL, json=payload, headers=headers)
        if not resp.ok:
            print(f"Error enviando mensaje a {numero}: {resp.text}")
    except Exception as e:
        print(f"Error en enviar_whatsapp: {str(e)}")

# --------- Consultar Ollama ----------
def consulta_ollama(prompt):
    try:
        payload = {
            'model': 'ana',
            'prompt': prompt,
            'stream': False
        }
        resp = requests.post(OLLAMA_URL, json=payload, timeout=30)
        if resp.ok:
            data = resp.json()
            return data.get('response', 'No entendí.')
        else:
            print(f"Error consultando Ollama: {resp.text}")
            return 'Hubo un error al procesar tu mensaje.'
    except Exception as e:
        print(f"Error en consulta_ollama: {str(e)}")
        return 'Hubo un error al procesar tu mensaje.'

# --------- Subir Excel con números ----------
@app.route('/sendNumbers', methods=['POST'])
def send_numbers():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No se encontró el archivo'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No se seleccionó archivo'}), 400
        
        df = pd.read_excel(file)
        if 'nombre' not in df.columns or 'número' not in df.columns:
            return jsonify({'error': 'El Excel debe tener columnas "nombre" y "número"'}), 400
        
        enviados = 0
        for _, row in df.iterrows():
            nombre = str(row['nombre']).strip()
            numero = str(row['número']).strip()
            
            if not numero or numero == 'nan':
                continue
                
            mensaje = f"Hola {nombre}, ¿nos das permiso para llamarte?"
            enviar_whatsapp(numero, mensaje)
            historial.setdefault(numero, []).append({'from': 'bot', 'text': mensaje})
            enviados += 1
        
        return jsonify({'status': f'{enviados} mensajes enviados'}), 200
    except Exception as e:
        print(f"Error en send_numbers: {str(e)}")
        return jsonify({'error': str(e)}), 400

# --------- Hacer llamada con Twilio y ElevenLabs ----------
def hacer_llamada(numero):
    try:
        texto_ia = consulta_ollama("El usuario ha aceptado la llamada. Genera un mensaje corto y amigable de saludo para una llamada telefónica.")
        audio_path = generar_audio_elevenlabs(texto_ia)
        if audio_path is None:
            print(f"No se pudo generar audio para {numero}")
            return
        
        filename = os.path.basename(audio_path)
        twiml_url = f"{SERVER_URL}/twiml/{filename}"
        
        call = client.calls.create(
            to=numero,
            from_=TWILIO_CALLER_ID,
            url=twiml_url,
            method='GET'
        )
        
        historial.setdefault(numero, []).append({
            'from': 'call', 
            'sid': call.sid, 
            'audio_file': filename,
            'message': texto_ia
        })
        print(f"Llamada iniciada a {numero}, SID: {call.sid}")
    except Exception as e:
        print(f"Error haciendo llamada a {numero}: {str(e)}")

# --------- Generar TwiML para la llamada ----------
@app.route('/twiml/<filename>', methods=['GET'])
def generate_twiml(filename):
    try:
        response = VoiceResponse()
        audio_url = f"{SERVER_URL}/audio/{filename}"
        response.play(audio_url)
        response.hangup()
        return str(response), 200, {'Content-Type': 'text/xml'}
    except Exception as e:
        print(f"Error generando TwiML: {str(e)}")
        response = VoiceResponse()
        response.say("Lo siento, hubo un error.")
        response.hangup()
        return str(response), 200, {'Content-Type': 'text/xml'}

# --------- Generar audio con ElevenLabs ----------
def generar_audio_elevenlabs(texto):
    try:
        headers = {
            'xi-api-key': ELEVENLABS_API_KEY,
            'Content-Type': 'application/json'
        }
        payload = {
            'text': texto,
            'voice_settings': {'stability': 0.5, 'similarity_boost': 0.75}
        }
        response = requests.post(
            f'https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}',
            headers=headers,
            json=payload,
            timeout=30
        )
        if response.ok:
            audio_filename = f'audio_{os.urandom(4).hex()}.mp3'
            audio_path = os.path.join('static', audio_filename)
            os.makedirs('static', exist_ok=True)
            with open(audio_path, 'wb') as f:
                f.write(response.content)
            return audio_path
        else:
            print(f"Error en ElevenLabs: {response.text}")
            return None
    except Exception as e:
        print(f"Error generando audio: {str(e)}")
        return None

# --------- Servir archivo de audio ----------
@app.route('/audio/<filename>', methods=['GET'])
def serve_audio(filename):
    try:
        file_path = os.path.join('static', filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='audio/mpeg')
        else:
            return jsonify({'error': 'Archivo no encontrado'}), 404
    except Exception as e:
        print(f"Error sirviendo audio: {str(e)}")
        return jsonify({'error': str(e)}), 400

# --------- Obtener historial ----------
@app.route('/history/<numero>', methods=['GET'])
def get_history(numero):
    return jsonify(historial.get(numero, []))

# --------- Endpoint de salud ----------
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'ok',
        'message': 'API funcionando correctamente',
        'endpoints': ['/webhook', '/sendNumbers', '/history/<numero>', '/audio/<filename>']
    })

if __name__ == '__main__':
    print("🚀 Iniciando API...")
    print(f"🔗 Webhook: {SERVER_URL}/webhook")
    print(f"📋 Health check: {SERVER_URL}/health")
    app.run(host='0.0.0.0', port=4000, debug=True)
