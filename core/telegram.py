import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _api_url(method):
    return f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"


def send_message(chat_id, text, parse_mode="HTML"):
    """
    Send a plain message to a Telegram chat_id.
    Returns the parsed JSON response from Telegram (a dict with an "ok" key),
    or a dict with ok=False if the request itself fails (e.g. network error).
    """
    try:
        response = requests.post(
            _api_url("sendMessage"),
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            },
            timeout=10,
        )
        data = response.json()
        if not data.get("ok"):
            logger.warning("Telegram sendMessage failed: %s", data)
        return data
    except requests.RequestException as exc:
        logger.exception("Telegram sendMessage request failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def send_otp(chat_id, code):
    """
    Send a one-time login code to the given chat_id.
    """
    text = f"Your verification code is: <b>{code}</b>\n\nThis code will expire shortly. Do not share it with anyone."
    return send_message(chat_id, text)