# Espacio Sommelier Virtual

Proyecto que integra un **avatar en tiempo real** con voz y transcripción automática, pensado para experiencias de degustación y presentación.  
El sistema combina un backend en Python (FastAPI + WebSocket) con un frontend en Vite/JavaScript que muestra el avatar y permite interacción por voz.

---

## 🚀 Funcionalidad principal
- **Avatar en streaming** (HeyGen) que habla en español.
- **Captura de micrófono** en el navegador y envío de audio al backend.
- **Transcripción incremental** con Whisper STT.
- **Orquestación de respuestas** vía LLM y flujo de negocio.
- **Visualización en vivo**: video del avatar + subtítulos con transcripción parcial.

---

## 📂 Estructura del proyecto
backend/   # Código Python (FastAPI, WebSocket, STT, orquestación)
frontend/  # Código JS (Vite, main.js, style.css, processor.js, index.html)
tests/     # Pruebas automatizadas
.github/   # Workflows de CI/CD (ci.yml, deploy.yml)
README.md    # Este archivo

Code

---

## ⚙️ Requisitos
- **Backend**: Python 3.10+, FastAPI, websockets, OpenAI SDK.
- **Frontend**: Node.js 18+, Vite.
- **Dependencias**: ver `requirements.txt` y `package.json`.

---

## ▶️ Cómo correr el proyecto

### Backend
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
./start_backend.sh
Frontend
bash
cd frontend
npm install
npm run dev
Abrir en el navegador: http://localhost:5173

🧩 Flujo de interacción
Usuario selecciona micrófono y hace clic en Iniciar Avatar.

El frontend abre un WebSocket y envía audio en PCM16.

El backend transcribe con Whisper y decide la respuesta.

El avatar habla la respuesta y se muestra la transcripción en pantalla.

🔄 CI/CD Pipeline
El proyecto cuenta con integración continua y despliegue automático:

mermaid
flowchart TD
    A[Push a main] --> B[CI Pipeline: Run tests]
    B -->|Tests OK| C[Deploy Pipeline: SSH to server]
    B -->|Tests FAIL| D[No deploy]
CI Pipeline: corre pytest para validar la lógica.

Deploy Pipeline: se ejecuta solo si el CI pasa en verde, hace git pull en el servidor y reinicia el servicio.

Esto asegura que nunca se despliegue código roto en producción.

📌 Notas
processor.js está en public/ para que el navegador lo cargue como AudioWorklet.

Los archivos de prueba y modelos antiguos (Vosk) fueron eliminados: el proyecto usa Whisper.

El repo está limpio y minimalista: solo código esencial y scripts de arranque.

👥 Autores
Rodrigo — Arquitectura, backend y frontend, idea, producción, conducción y ejecución con algunas otras cositas que terminan en ción pero no tantas.