#!/bin/bash

# Matar cualquier proceso que esté usando el puerto 8000
fuser -k 8000/tcp

# Exportar todas las variables definidas en .env
set -a
source ../.env
set +a

# Activar entorno virtual si lo usás
source venv/bin/activate

# Configuración de Uvicorn
UVICORN_WORKERS=1
UVICORN_HOST=0.0.0.0
UVICORN_PORT=8000

# Levantar el backend con uvicorn apuntando a server.py
cd ..
exec uvicorn backend.server:app \
  --host $UVICORN_HOST \
  --port $UVICORN_PORT \
  --workers $UVICORN_WORKERS \
  --log-level debug \
  --reload
