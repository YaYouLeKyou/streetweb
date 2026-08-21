from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
from timedelta import timedelta

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


def _format_date(iso_str: str) -> str:
    """Convertit une date ISO (UTC) en format lisible en heure de Paris."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        paris_dt = dt.astimezone(get_paris_tz())
        return paris_dt.strftime("%d/%m/%Y à %H:%M")
    except (ValueError, TypeError):
        return iso_str

def _extract_and_format_date(item):
    """Extrait la date quelle que soit la clé utilisée dans le dictionnaire."""
    if not isinstance(item, dict):
        return ""
    raw_date = (
        item.get("published_at") 
        or item.get("publishedAt") 
        or item.get("created_at") 
        or item.get("date") 
        or ""
    )
    return _format_date(str(raw_date)) if raw_date else ""