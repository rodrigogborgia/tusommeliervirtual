import logging
from config import NEW_RELIC_ENABLED

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("backend")

try:
    import newrelic.agent as nr
except Exception:
    nr = None

def record_event(event_type: str, payload: dict):
    if NEW_RELIC_ENABLED and nr:
        try:
            nr.record_custom_event(event_type, payload)
        except Exception as e:
            log.warning(f"NR event failed: {e}")
