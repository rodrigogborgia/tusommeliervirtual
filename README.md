# 🍷 Tu Sommelier Virtual – Backend

Este proyecto implementa un pipeline de ingesta de PDFs en **ChromaDB** para consultas semánticas en español.

---

## 🚀 Ingesta de PDFs

1. Colocar los archivos PDF en la carpeta:

backend/pdfs/

2. Ejecutar la ingesta en segundo plano:

nohup python -u backend/ingest_all.py > ingest.log 2>&1 &

3. Monitorear el progreso en tiempo real con timestamps:

tail -f ingest.log | awk '{ print strftime("[%Y-%m-%d %H:%M:%S]"), $0 }'

4. Verificar el número de documentos ya procesados:

python backend/check_ingest.py

📊 Logs y chunks
Cada PDF se divide en chunks (fragmentos de texto) que se indexan en ChromaDB.

El log muestra:

[INFO] Procesando: ... → inicio de un PDF.

[OK] Ingestado: {...} → PDF terminado con cantidad de chunks.

[INFO] Total documentos ahora: X → contador acumulado.

⚠️ Nota importante
Los resultados de la ingesta (colección ChromaDB) NO se versionan en GitHub.

El repositorio contiene únicamente los scripts y configuración necesarios para regenerar la base.

Para reconstruir la colección, basta con volver a ejecutar ingest_all.py con los PDFs en la carpeta backend/pdfs/.

🛠️ Dependencias
Instalar las dependencias desde requirements.txt:

pip install -r requirements.txt

✅ Estado actual
Ingesta estable validada en VPS.

10 PDFs procesados con éxito en la colección ChromaDB.

Scripts versionados en GitHub para reproducibilidad.


---
