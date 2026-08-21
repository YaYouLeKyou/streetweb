from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union

@ app.route("/")
def index():
    """Page principale : affiche le dernier post + historique."""
    try:
        latest = news_service.get_latest_news()
        history = news_service.get_all_news(limit=20)
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des news sur la page d'accueil : {e}")
        latest = None
        history = []
    # Formatage des dates pour l'affichage
    if latest and isinstance(latest, dict):
        latest["published_at_display"] = _extract_and_format_date(latest)
    if history and isinstance(history, list):
        for item in history:
            if isinstance(item, dict):
                item["published_at_display"] = _extract_and_format_date(item)
    # Autres variables (stats, intervals, etc.)


def _format_date(date_val):
    """Convertit une date ISO, un timestamp ou un objet datetime en format lisible JJ/MM/AAAA HH:MM."""
    if not date_val:
        return ""
    try:
        if isinstance(date_val, datetime):
            return date_val.strftime("%d/%m/%Y %H:%M")

        clean_str = str(date_val).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(date_val)

def _extract_and_format_date(item):
    """Extrait la date disponible et la formate proprement."""
    if not isinstance(item, dict):
        return ""

    raw_date = (
        item.get("published_at")
        or item.get("publishedAt")
        or item.get("created_at")
        or item.get("date")
        or ""
    )
    return _format_date(raw_date) if raw_date else ""