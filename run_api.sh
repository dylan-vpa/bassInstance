#!/bin/bash
set -e  # Si falla algo, se detiene

echo "🐍 Configurando entorno virtual Python..."
if [ ! -d "venv" ]; then
    echo "📦 Creando entorno virtual..."
    python3 -m venv venv
fi

echo "🔌 Activando entorno virtual..."
source venv/bin/activate

echo "🔧 Instalando dependencias..."
pip install -r requirements.txt

echo "📁 Verificando archivo .env..."
if [ ! -f .env ]; then
    echo "⚠️  Archivo .env no encontrado."
    echo "📋 Copiando .env.example a .env..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✏️  Por favor, edita el archivo .env con tus credenciales antes de continuar."
        exit 1
    else
        echo "❌ Tampoco se encontró .env.example. Créalo manualmente."
        exit 1
    fi
fi

echo "🔍 Verificando variables críticas..."
source .env
if [[ -z "$WHATSAPP_TOKEN" || -z "$TWILIO_ACCOUNT_SID" || -z "$ELEVENLABS_API_KEY" ]]; then
    echo "⚠️  Faltan variables críticas en .env. Verifica:"
    echo "   - WHATSAPP_TOKEN"
    echo "   - TWILIO_ACCOUNT_SID" 
    echo "   - ELEVENLABS_API_KEY"
    exit 1
fi

echo "📁 Creando directorio static..."
mkdir -p static

echo "🌐 Exportando variables de entorno..."
export FLASK_APP=main.py
export FLASK_ENV=development

echo "🚀 Levantando API en puerto 4000..."
echo "🔗 Webhook: http://localhost:4000/webhook"
echo "📋 Health check: http://localhost:4000/health"
echo "📊 Para probar: curl http://localhost:4000/health"

python main.py
