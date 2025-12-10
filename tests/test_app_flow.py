import json
from pathlib import Path
import qa_log
import app_flow
import llm_client

def test_entrenar_confirmar_presentar(tmp_path, monkeypatch):
    qa_log.LOG_FILE = str(tmp_path / "qa_log.json")

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

def test_presentar_calls_llm_if_not_in_log(tmp_path, monkeypatch):
    qa_log.LOG_FILE = str(tmp_path / "qa_log.json")
    monkeypatch.setattr(llm_client, "ask_llm", lambda query, instruction=None: "LLM_FALLBACK")

    res = app_flow.main(mode="Presentar", query="nuevo")
    assert res["respuesta"] == "LLM_FALLBACK"
