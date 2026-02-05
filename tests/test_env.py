import os
import pytest
from dotenv import load_dotenv

def _load_env_for_tests():
    # Soporta dev local (repo/.env) y prod (/opt/...), o bien variables ya exportadas.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.getenv("ENV_PATH"),
        os.path.join(repo_root, "env"),
        os.path.join(repo_root, ".env"),
        "/opt/tusommeliervirtual.com/.env",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            load_dotenv(dotenv_path=p)
            return
    load_dotenv()

_load_env_for_tests()

REQUIRED_ENV_VARS = [
    "HEYGEN_API_KEY",
    "OPENAI_API_KEY",
    "AVATAR_ID",
    "VOICE_ID",
    "LANGUAGE",
]

@pytest.mark.parametrize("var", REQUIRED_ENV_VARS)
def test_env_variables_present(var):
    value = os.getenv(var)
    assert value is not None and value.strip() != "", f"Variable {var} no está definida"
