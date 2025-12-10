import json
from pathlib import Path
import qa_log

def test_save_interaction_replaces(tmp_path):
    qa_log.LOG_FILE = str(tmp_path / "qa_log.json")

    # Primera entrada
    qa_log.save_interaction("bife", "respuesta1", None)
    # Reemplazo
    qa_log.save_interaction("bife", "respuesta2", "corrección")

    lines = Path(qa_log.LOG_FILE).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["response"] == "respuesta2"
    assert entry["correction"] == "corrección"

def test_find_in_log_returns_latest(tmp_path):
    qa_log.LOG_FILE = str(tmp_path / "qa_log.json")
    entries = [
        {"query": "ojo de bife", "response": "vieja", "correction": None},
        {"query": "ojo de bife", "response": "nueva", "correction": "corr"}
    ]
    with open(qa_log.LOG_FILE, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    result = qa_log.find_in_log("ojo de bife")
    assert result["response"] == "nueva"
    assert result["correction"] == "corr"
