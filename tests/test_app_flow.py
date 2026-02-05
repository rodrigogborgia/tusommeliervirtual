import json
from pathlib import Path
import qa_log
import backend.app_flow as app_flow
from backend import llm_client

def test_save_interaction_replaces_jsonl(tmp_path, monkeypatch):
    # Parchear la ruta de LOG_FILE_JSONL para que apunte al tmp_path
    monkeypatch.setattr(qa_log, "LOG_FILE_JSONL", str(tmp_path / "qa_log.jsonl"))

    # Mock del LLM
    monkeypatch.setattr(llm_client, "ask_llm", lambda query, instruction=None: "RESPUESTA_LLM")

    # Entrenar
    res = app_flow.main(mode="Entrenar", query="bife")
    assert res["respuesta"] == "RESPUESTA_LLM"

    # Confirmar
    res = app_flow.main(mode="Confirmar", query="bife", response="vieja", correction="corr")
    assert res["respuesta"] == "corr"

    # Presentar
    res = app_flow.main(mode="Presentar", query="bife")
    assert res["respuesta"] == "corr"

    # Verificar que la última entrada en el log corresponde a la corrección
    lines = Path(qa_log.LOG_FILE_JSONL).read_text(encoding="utf-8").splitlines()
    data = [json.loads(line) for line in lines]
    assert data[-1]["response"] == "vieja"
    assert data[-1]["correction"] == "corr"

def test_presentar_calls_llm_if_not_in_log(tmp_path, monkeypatch):
    # Parchear la ruta de LOG_FILE_JSONL para que apunte al tmp_path
    monkeypatch.setattr(qa_log, "LOG_FILE_JSONL", str(tmp_path / "qa_log.jsonl"))

    # Mock del LLM
    monkeypatch.setattr(llm_client, "ask_llm", lambda query, instruction=None: "LLM_FALLBACK")

    res = app_flow.main(mode="Presentar", query="nuevo")
    assert res["respuesta"] == "LLM_FALLBACK"
