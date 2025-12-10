import json
import os

LOG_FILE = "qa_log.json"
CLEAN_FILE = "qa_log_clean.json"

def clean_log():
    if not os.path.exists(LOG_FILE):
        print("No existe qa_log.json")
        return

    entries_by_query = {}

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)

                # Ignorar entradas inválidas
                if entry.get("response") is None and entry.get("correction") is None:
                    continue

                # Siempre sobrescribir: nos quedamos con la última versión
                entries_by_query[entry["query"]] = entry
            except json.JSONDecodeError:
                continue

    # Guardar archivo limpio
    with open(CLEAN_FILE, "w", encoding="utf-8") as f:
        for e in entries_by_query.values():
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"Log limpio guardado en {CLEAN_FILE}")

if __name__ == "__main__":
    clean_log()
