import json
import os
import unicodedata
import re
from rapidfuzz import fuzz

LOG_FILE = "qa_log.json"

def normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text

def save_interaction(query: str, response: str, correction: str = None):
    entry = {"query": query, "response": response, "correction": correction}

    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return

    entries = []
    replaced = False
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
                if e.get("query") == query:
                    entries.append(entry)
                    replaced = True
                else:
                    entries.append(e)
            except json.JSONDecodeError:
                continue

    if not replaced:
        entries.append(entry)

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

def find_in_log(query: str, threshold: int = 80):
    if not os.path.exists(LOG_FILE):
        return None

    normalized_query = normalize(query)
    best_match = None
    best_score = 0

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("response") is None and entry.get("correction") is None:
                    continue

                candidate = normalize(entry["query"])
                score = fuzz.ratio(normalized_query, candidate)

                if score >= threshold and score >= best_score:
                    best_score = score
                    best_match = entry
            except json.JSONDecodeError:
                continue

    return best_match
