📘 Guía rápida: Ciclo de Entrenar, Confirmar y Presentar
🎯 Objetivo
Mantener un flujo claro y reproducible para entrenar, confirmar y presentar respuestas en el backend, evitando duplicados en el log (qa_log.json).

⚙️ Componentes principales
qa_log.py

normalize(text): limpia y normaliza queries.

save_interaction(query, response, correction): guarda o reemplaza entradas en el log.

find_in_log(query, threshold): busca coincidencias con fuzzy matching.

app_flow.py

main(mode, query, response, correction): coordina los modos de operación.

Entrenar → consulta al LLM y guarda la respuesta.

Confirmar → guarda la corrección, reemplazando la entrada existente.

Presentar → busca en el log y devuelve la corrección o respuesta; si no existe, consulta al LLM.

server.py

Expone endpoints REST (/api/query, /api/session, /api/speak).

Llama a app_flow.main para ejecutar la lógica.

🔄 Flujo de trabajo
Entrenar

Input: {"mode":"Entrenar","query":"..."}

Acción: consulta al LLM y guarda la respuesta en el log.

Resultado: una sola entrada por query.

Confirmar

Input: {"mode":"Confirmar","query":"...","response":"...","correction":"..."}

Acción: reemplaza la entrada existente con la corrección.

Resultado: la query queda actualizada con la última versión.

Presentar

Input: {"mode":"Presentar","query":"..."}

Acción: busca en el log; si existe, devuelve la corrección o respuesta.

Si no existe, consulta al LLM (pero no guarda).

🧹 Mantenimiento del log
qa_log_cleaner.py

Elimina duplicados y entradas inválidas.

Genera qa_log_clean.json con una sola versión por query.

Puede ejecutarse manualmente o programarse con cron.

✅ Ejemplo de uso con curl
bash
# Entrenar
curl -X POST http://localhost:8000/api/query \
     -H "Content-Type: application/json" \
     -d '{"mode":"Entrenar","query":"¿Cuál es el maridaje ideal para un ojo de bife?"}'

# Confirmar
curl -X POST http://localhost:8000/api/query \
     -H "Content-Type: application/json" \
     -d '{"mode":"Confirmar","query":"¿Cuál es el maridaje ideal para un ojo de bife?","response":"Un ojo de bife combina bien con vinos tintos robustos.","correction":"Recomiendo un Malbec argentino, por su cuerpo y notas frutales."}'

# Presentar
curl -X POST http://localhost:8000/api/query \
     -H "Content-Type: application/json" \
     -d '{"mode":"Presentar","query":"¿Cuál es el maridaje ideal para un ojo de bife?"}'
