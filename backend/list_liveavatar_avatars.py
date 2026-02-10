r"""
Lista avatares públicos y de tu cuenta en Live Avatar para obtener UUIDs.
Ejecutar desde la raíz: backend\venv\Scripts\python.exe backend/list_liveavatar_avatars.py
"""
import os
import sys
import json
import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(REPO_ROOT, "env")
if os.path.exists(env_path):
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path)

API_KEY = os.getenv("LIVEAVATAR_API_KEY")
if not API_KEY:
    print("Falta LIVEAVATAR_API_KEY en env")
    sys.exit(1)

BASE = "https://api.liveavatar.com"
headers = {"X-API-KEY": API_KEY, "Accept": "application/json"}

# Avatares públicos
print("=== Avatares públicos ===\n")
r = requests.get(f"{BASE}/v1/avatars/public", headers=headers, timeout=15)
if r.status_code != 200:
    print("Error", r.status_code, r.text[:500])
else:
    data = r.json()
    avatars = data.get("data") or data.get("avatars") or []
    if isinstance(avatars, list):
        for i, a in enumerate(avatars[:20]):
            aid = a.get("avatar_id") or a.get("id")
            name = a.get("name") or a.get("display_name") or ""
            print(f"  {i+1}. {aid}  {name}")
        if len(avatars) > 20:
            print(f"  ... y {len(avatars) - 20} más")
    else:
        print(json.dumps(data, indent=2)[:2000])

# Avatares de tu cuenta (privados)
print("\n=== Avatares de tu cuenta ===\n")
r2 = requests.get(f"{BASE}/v1/avatars", headers=headers, timeout=15)
if r2.status_code != 200:
    print("Error", r2.status_code, r2.text[:500])
else:
    data2 = r2.json()
    avatars2 = data2.get("data") or data2.get("avatars") or []
    if isinstance(avatars2, list):
        for i, a in enumerate(avatars2[:20]):
            aid = a.get("avatar_id") or a.get("id")
            name = a.get("name") or a.get("display_name") or ""
            print(f"  {i+1}. {aid}  {name}")
        if len(avatars2) > 20:
            print(f"  ... y {len(avatars2) - 20} más")
    else:
        print(json.dumps(data2, indent=2)[:2000])
