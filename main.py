import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify
from whatsapp import WhatsAppClient
from dotenv import load_dotenv
import ollama
import pandas as pd
from werkzeug.utils import secure_filename

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Configuración de la API de WhatsApp
TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
OLLAMA_MODEL = "llama3.1"

# Configuración de Flask
app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"xlsx", "xls"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Crear carpeta para subir archivos si no existe
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Inicializar cliente de WhatsApp
whatsapp_client = WhatsAppClient(TOKEN, PHONE_NUMBER_ID)

# Configurar base de datos SQLite (como en el script anterior)
DB_PATH = "conversations.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_number TEXT NOT NULL,
            message_type TEXT NOT NULL,
            message_content TEXT NOT NULL,
            timestamp DATETIME NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_message(user_number, message_type, message_content):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO conversations (user_number, message_type, message_content, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (user_number, message_type, message_content, datetime.now()))
    conn.commit()
    conn.close()

def get_conversation_history(user_number, limit=5):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT message_type, message_content
        FROM conversations
        WHERE user_number = ?
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (user_number, limit))
    history = cursor.fetchall()
    conn.close()
    return history[::-1]

def get_ollama_response(user_number, message, nombre=""):
    try:
        history = get_conversation_history(user_number)
        messages = [
            {"role": "system", "content": f"Eres un asistente útil que responde de manera clara y amigable. Personaliza el mensaje con el nombre del usuario si se proporciona ({nombre})."}
        ]
        for msg_type, msg_content in history:
            role = "user" if msg_type == "incoming" else "assistant"
            messages.append({"role": role, "content": msg_content})
        messages.append({"role": "user", "content": message})
        response = ollama.chat(model=OLLAMA_MODEL, messages=messages)
        return response['message']['content']
    except Exception as e:
        return f"Error al generar respuesta: {str(e)}"

def allowed_file(filename):
    """Verifica si el archivo tiene una extensión permitida."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# Nuevo endpoint para subir archivo Excel y enviar mensajes
@app.route("/sendNumbers", methods=["POST"])
def send_numbers():
    # Verificar si se envió un archivo
    if "file" not in request.files:
        return jsonify({"error": "No se proporcionó un archivo"}), 400
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No se seleccionó un archivo"}), 400
    
    # Verificar si el archivo tiene una extensión válida
    if not allowed_file(file.filename):
        return jsonify({"error": "Formato de archivo no válido. Use .xlsx o .xls"}), 400
    
    # Guardar el archivo temporalmente
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)
    
    try:
        # Leer el archivo Excel
        df = pd.read_excel(file_path)
        
        # Validar columnas
        expected_columns = ["nombre", "numero"]
        if not all(col in df.columns for col in expected_columns):
            return jsonify({"error": "El archivo debe tener las columnas 'nombre' y 'numero'"}), 400
        
        results = []
        # Procesar cada fila
        for index, row in df.iterrows():
            nombre = str(row["nombre"]).strip()
            numero = str(row["numero"]).strip()
            
            # Validar número
            if not numero.isdigit():
                results.append({"nombre": nombre, "numero": numero, "status": "error", "message": "Número inválido"})
                continue
            
            # Generar mensaje personalizado
            message = f"Hola {nombre}, ¿en qué puedo ayudarte hoy?"
            
            # Obtener respuesta de Ollama
            response_text = get_ollama_response(numero, message, nombre)
            
            # Guardar mensaje en la base de datos
            save_message(numero, "outgoing", message)
            save_message(numero, "outgoing", response_text)
            
            # Enviar mensaje a través de WhatsApp
            try:
                whatsapp_client.send_message(
                    to=numero,
                    message=response_text,
                    preview_url=False
                )
                results.append({"nombre": nombre, "numero": numero, "status": "success", "message": response_text})
            except Exception as e:
                results.append({"nombre": nombre, "numero": numero, "status": "error", "message": str(e)})
        
        # Eliminar archivo temporal
        os.remove(file_path)
        
        return jsonify({"status": "success", "results": results}), 200
    
    except Exception as e:
        # Eliminar archivo en caso de error
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({"error": f"Error al procesar el archivo: {str(e)}"}), 500

# Resto del script (webhook, send_message, etc.) se omite por brevedad, pero debe incluirse
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification token mismatch", 403

@app.route("/webhook", methods=["POST"])
def handle_webhook():
    data = request.get_json()
    if "entry" in data and len(data["entry"]) > 0:
        entry = data["entry"][0]
        if "changes" in entry and len(entry["changes"]) > 0:
            change = entry["changes"][0]
            if "value" in change and "messages" in change["value"]:
                for message in change["value"]["messages"]:
                    if message["type"] == "text":
                        from_number = message["from"]
                        text = message["text"]["body"]
                        save_message(from_number, "incoming", text)
                        response_text = get_ollama_response(from_number, text)
                        save_message(from_number, "outgoing", response_text)
                        whatsapp_client.send_message(
                            to=from_number,
                            message=response_text,
                            preview_url=False
                        )
    return jsonify({"status": "success"}), 200

@app.route("/send_message", methods=["POST"])
def send_message():
    data = request.get_json()
    to_number = data.get("to")
    message = data.get("message")
    if not to_number or not message:
        return jsonify({"error": "Se requiere 'to' y 'message'"}), 400
    response_text = get_ollama_response(to_number, message)
    save_message(to_number, "outgoing", response_text)
    whatsapp_client.send_message(
        to=to_number,
        message=response_text,
        preview_url=False
    )
    return jsonify({"status": "success", "response": response_text}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
