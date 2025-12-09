set -a
source .env
set +a
source venv/bin/activate
uvicorn app:app --host 0.0.0.0 --port 8080
