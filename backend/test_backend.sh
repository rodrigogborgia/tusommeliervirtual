#!/bin/bash
# test_backend.sh - corre los tests unitarios del backend

# Activar el entorno virtual
source venv/bin/activate

# Ir a la raíz del proyecto (un nivel arriba)
cd "$(dirname "$0")/.."

# Ejecutar pytest con el path correcto
PYTHONPATH=backend pytest -q tests/
