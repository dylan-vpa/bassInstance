#!/bin/bash
set -e  # Si falla algo, se detiene

echo "Instalando dependencias..."
pip3 install -r requirements.txt

echo "Verificando archivo .env..."
if [ ! -f .env ]; then
    echo "⚠️  Archivo .env no encontrado. Por favor, crea uno antes de continuar."
    exit 1
fi

echo "Exportando variables de entorno..."
export FLASK_APP=main.py
export FLASK_ENV=production

echo "Levantando API en puerto 4000..."
flask run --host=0.0.0.0 --port=4000
