from flask import Flask, render_template, jsonify
session = Flask(__name__)
app = session

import news_service
import logger

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union

def _format_date(date_val):
    if not date_val:
        return ""
    try:
        clean_str = str(date_val).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(date_val)

def _extract_and_format_date(item):
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

@app.route("/")
def index():
    try:
        latest = news_service.get_latest_news()
        history = news_service.get_all_news(limit=20)
    except Exception as e:
        pass
    
    if latest and isinstance(latest, dict):
        latest["published_at_display"] = _extract_and_format_date(latest)
    if history and isinstance(history, list):
        for item in history:
            if isinstance(item, dict):
                item["published_at_display"] = _extract_and_format_date(item)
    
    return render_template("index.html")

@app.route("/ping")
def ping():
    return jsonify({"status": "ok"})

def _build_long_post_message(news: dict) -> str:
    if not news:
        return ""
    title = news.get("title", "")
    breaking = news.get("breaking_text", "")
    url = news.get("url", "")
    return f"{title}\n\n{breaking}\n\nLire l'article complet : {url}"

def run_web_server(host: str = "0.0.0.0", port: int = 5000):
    app.run(host=host, port=port)