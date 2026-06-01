# alerts/whatsapp.py
import requests
from plutus.config import settings


def send_whatsapp(message: str) -> bool:
    """Send via CallMeBot API (free, personal WhatsApp only)."""
    if not settings.WHATSAPP_ENABLED:
        return False

    url = "https://api.callmebot.com/whatsapp.php"
    params = {
        "phone": settings.WHATSAPP_PHONE,
        "text": message,
        "apikey": settings.WHATSAPP_API_KEY,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False
