#!/bin/bash

echo "Instalando dependencias..."
pip install -r requirements.txt

echo "Exportando variables de entorno..."
export FLASK_APP=app.py
export FLASK_ENV=production

echo "Levantando API en puerto 4000..."
flask run --host=0.0.0.0 --port=4000
