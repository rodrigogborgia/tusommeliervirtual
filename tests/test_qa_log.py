import json
from pathlib import Path
import qa_log

def test_save_interaction_replaces(tmp_path, monkeypatch):
    # Parchear la ruta de LOG_FILE_JSONL para que apunte al tmp_path
    monkeypatch.setattr(qa_log, "LOG_FILE_JSONL", str(tmp_path / "qa_log.jsonl"))

    # Crear instancia de QALog
    logger = qa_log.QALog()

    # Primera entrada
    logger.save_interaction("bife", "respuesta1", None)
    # Reemplazo
    logger.save_interaction("bife", "respuesta2", "corrección")

    # Leer el archivo como JSONL (una entrada por línea)
    lines = Path(qa_log.LOG_FILE_JSONL).read_text(encoding="utf-8").splitlines()
    data = [json.loads(line) for line in lines]

    # Tomamos la última entrada
    assert data[-1]["response"] == "respuesta2"
    assert data[-1]["correction"] == "corrección"
