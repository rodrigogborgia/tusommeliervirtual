import time
import logging
import json
import os
from logging.handlers import RotatingFileHandler

def _default_log_dir() -> str:
    # En Linux/producción se suele usar /var/log, en Windows eso falla.
    if os.getenv("LOG_DIR"):
        return os.getenv("LOG_DIR")
    if os.name == "nt":
        return os.path.join(os.getcwd(), "logs")
    return "/var/log/sommelier"

LOG_DIR = _default_log_dir()
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except Exception:
    # Fallback seguro si no hay permisos (p.ej. /var/log sin sudo)
    LOG_DIR = os.path.join(os.getcwd(), "logs")
    os.makedirs(LOG_DIR, exist_ok=True)

# Archivos de log
LOG_FILE_JSONL = os.path.join(LOG_DIR, "qa_log.jsonl")
LOG_FILE_PERF = os.path.join(LOG_DIR, "qa_performance.log")

# Configuración de logging con rotación automática (5 MB, sin backups)
handler = RotatingFileHandler(LOG_FILE_PERF, maxBytes=5*1024*1024, backupCount=0)
formatter = logging.Formatter("%(asctime)s - %(message)s")
handler.setFormatter(formatter)

logging.basicConfig(level=logging.INFO, handlers=[handler])

class QALog:
    def __init__(self):
        self.marks = {}

    def mark(self, label: str):
        self.marks[label] = time.time()
        logging.info(f"MARK: {label}")

    def diff(self, start: str, end: str):
        if start in self.marks and end in self.marks:
            delta = self.marks[end] - self.marks[start]
            logging.info(f"DIFF {start} -> {end}: {delta:.3f}s")
            return delta
        else:
            logging.warning(f"Missing marks for {start} or {end}")
            return None

    def save_interaction(self, query: str, response: str, correction: str = None, client_metrics: dict = None):
        """Guarda interacción. Si client_metrics viene del frontend, se usan esas métricas."""
        if client_metrics is not None:
            # Usar solo métricas del frontend, sin llamar diff() (evita "Missing marks")
            metrics = {k: v for k, v in client_metrics.items() if v is not None}
            self._log_qa_metrics_readable(metrics)
        else:
            # Flujo legacy: marks del backend
            metrics = {
                "stt_time": self.diff("stt_start", "stt_done"),
                "llm_time": self.diff("llm_start", "llm_done"),
                "avatar_time": self.diff("avatar_start", "avatar_done"),
                "interaction_time": self.diff("interaction_start", "interaction_end"),
            }
        entry = {
            "timestamp": time.time(),
            "query": query,
            "response": response,
            "correction": correction,
            "metrics": metrics
        }
        try:
            with open(LOG_FILE_JSONL, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            q_preview = (query[:50] + "...") if len(query) > 50 else query
            r_preview = (response[:50] + "...") if len(response) > 50 else response
            logging.info(f"Saved interaction: {q_preview} -> {r_preview}")
        except Exception as e:
            logging.error(f"Error saving interaction: {e}")

    def _log_qa_metrics_readable(self, m: dict):
        """Escribe en el log un resumen legible de las métricas QA."""
        lines = []
        if m.get("speech_start_ts") is not None:
            lines.append(f"user_init_talk mark={m['speech_start_ts']:.0f}")
        if m.get("speech_end_ts") is not None:
            lines.append(f"user_end_talk mark={m['speech_end_ts']:.0f}")
        if m.get("speech_duration_ms") is not None:
            lines.append(f"user_speech_duration={m['speech_duration_ms']}ms")
        if m.get("llm_time_ms") is not None:
            lines.append(f"chatgpt_query_duration={m['llm_time_ms']}ms")
        if m.get("response_received_ts") is not None:
            lines.append(f"response_received mark={m['response_received_ts']:.0f}")
        if m.get("speak_requested_ts") is not None:
            lines.append(f"heygen_speak_requested mark={m['speak_requested_ts']:.0f}")
        if m.get("avatar_start_ts") is not None:
            lines.append(f"heygen_init_talk mark={m['avatar_start_ts']:.0f}")
        if m.get("heygen_latency_ms") is not None:
            lines.append(f"heygen_latency={m['heygen_latency_ms']}ms")
        if lines:
            logging.info("QA_METRICS: " + " | ".join(lines))

    def find_in_log(self, query: str = None, response: str = None, since: float = None):
        """
        Busca entradas en el log por query, response o timestamp mínimo.
        """
        results = []
        if not os.path.exists(LOG_FILE_JSONL):
            return results

        try:
            with open(LOG_FILE_JSONL, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    if query and entry.get("query") == query:
                        results.append(entry)
                    elif response and entry.get("response") == response:
                        results.append(entry)
                    elif since and entry.get("timestamp", 0) >= since:
                        results.append(entry)
            return results
        except Exception as e:
            logging.error(f"Error reading log file: {e}")
            return []
