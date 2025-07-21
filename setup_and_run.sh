#!/bin/bash

# Script para instalar dependencias, configurar el entorno y ejecutar el bot de WhatsApp con Ollama

# Colores para mensajes en la terminal
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # Sin color

# Función para verificar si un comando está instalado
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}Error: $1 no está instalado${NC}"
        exit 1
    fi
}

# Función para verificar si un archivo existe
check_file() {
    if [ ! -f "$1" ]; then
        echo -e "${RED}Error: $1 no existe${NC}"
        exit 1
    fi
}

echo -e "${YELLOW}Iniciando configuración del entorno para el bot de WhatsApp con Ollama...${NC}"

# 1. Verificar dependencias del sistema
echo -e "${GREEN}Verificando dependencias del sistema...${NC}"
check_command python3
check_command pip3
check_command curl
check_command unzip

# 2. Instalar Ollama
if ! command -v ollama &> /dev/null; then
    echo -e "${GREEN}Instalando Ollama...${NC}"
    curl -fsSL https://ollama.com/install.sh | sh
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error al instalar Ollama${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}Ollama ya está instalado${NC}"
fi

# 3. Descargar el modelo de Ollama (llama3.1)
echo -e "${GREEN}Descargando el modelo llama3.1...${NC}"
ollama pull llama3.1
if [ $? -ne 0 ]; then
    echo -e "${RED}Error al descargar el modelo llama3.1${NC}"
    exit 1
fi

# 4. Iniciar el servidor de Ollama en segundo plano
echo -e "${GREEN}Iniciando el servidor de Ollama...${NC}"
ollama serve &
OLLAMA_PID=$!
sleep 5 # Esperar a que el servidor inicie
if ! ps -p $OLLAMA_PID > /dev/null; then
    echo -e "${RED}Error: No se pudo iniciar el servidor de Ollama${NC}"
    exit 1
fi

# 5. Instalar dependencias de Python
echo -e "${GREEN}Instalando dependencias de Python...${NC}"
pip3 install flask python-whatsapp-bot requests python-dotenv ollama pandas openpyxl
if [ $? -ne 0 ]; then
    echo -e "${RED}Error al instalar dependencias de Python${NC}"
    exit 1
fi

# 6. Crear archivo .env si no existe
echo -e "${GREEN}Configurando el archivo .env...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creando archivo .env. Por favor, edítalo con tus credenciales.${NC}"
    cat << EOF > .env
WHATSAPP_TOKEN=tu_token_de_whatsapp
PHONE_NUMBER_ID=tu_phone_number_id
VERIFY_TOKEN=tu_token_de_verificación
EOF
else
    echo -e "${GREEN}El archivo .env ya existe. Asegúrate de que contenga las credenciales correctas.${NC}"
fi

# 7. Verificar la existencia del script de Python
check_file "whatsapp_bot.py"

# 8. Instalar ngrok si no está presente
if ! command -v ngrok &> /dev/null; then
    echo -e "${GREEN}Instalando ngrok...${NC}"
    curl -s https://ngrok-agent.s3.amazonaws.com/ngrok-stable-linux-amd64.zip -o ngrok.zip
    unzip ngrok.zip
    chmod +x ngrok
    mv ngrok /usr/local/bin/
    rm ngrok.zip
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error al instalar ngrok${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}ngrok ya está instalado${NC}"
fi

# 9. Iniciar el servidor Flask
echo -e "${GREEN}Iniciando el servidor Flask...${NC}"
python3 whatsapp_bot.py &
FLASK_PID=$!
sleep 5
if ! ps -p $FLASK_PID > /dev/null; then
    echo -e "${RED}Error: No se pudo iniciar el servidor Flask${NC}"
    exit 1
fi

# 10. Iniciar ngrok para exponer el servidor
echo -e "${GREEN}Iniciando ngrok para exponer el puerto 5000...${NC}"
ngrok http 5000 &
NGROK_PID=$!
sleep 5
if ! ps -p $NGROK_PID > /dev/null; then
    echo -e "${RED}Error: No se pudo iniciar ngrok${NC}"
    exit 1
fi

# 11. Obtener la URL de ngrok
echo -e "${GREEN}Obteniendo la URL de ngrok...${NC}"
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o 'https://[^"]*' | head -n 1)
if [ -z "$NGROK_URL" ]; then
    echo -e "${RED}Error: No se pudo obtener la URL de ngrok${NC}"
    exit 1
fi
echo -e "${GREEN}URL del webhook: ${NGROK_URL}/webhook${NC}"
echo -e "${YELLOW}Configura esta URL en el panel de WhatsApp Business API${NC}"

# 12. Recordatorio para configurar el webhook
echo -e "${YELLOW}Por favor, configura el webhook en el panel de Meta con la URL: ${NGROK_URL}/webhook y el VERIFY_TOKEN del archivo .env${NC}"

# 13. Mantener el script en ejecución
echo -e "${GREEN}El bot está en ejecución. Presiona Ctrl+C para detenerlo.${NC}"
wait $FLASK_PID
