"""
Base de données SQLite locale — anti-doublons.

Stocke les liens d'articles déjà traités afin d'éviter
de republier la même actualité sur Twitter/X.
"""

import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional

import config

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Schéma de la table
# ─────────────────────────────────────────────────────────────
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS processed_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    source TEXT,
    tweet_text TEXT,
    published_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_BREAKING_NEWS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS breaking_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT,
    summary TEXT,
    breaking_text TEXT,
    secondary_proposals TEXT,
    published_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_connection() -> sqlite3.Connection:
    """Retourne une connexion SQLite (avec vérification des clés étrangères)."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    """Initialise la base de données et crée les tables si nécessaire."""
    conn = get_connection()
    try:
        conn.execute(CREATE_TABLE_SQL)
        conn.execute(CREATE_BREAKING_NEWS_TABLE_SQL)
        conn.commit()
        logger.info("Base de données initialisée : %s", config.DB_PATH)
    finally:
        conn.close()


def is_article_processed(url: str) -> bool:
    """
    Vérifie si un lien d'article a déjà été traité.

    :param url: URL canonique de l'article
    :return: True si déjà traité, False sinon
    """
    if not url:
        return False
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT 1 FROM processed_articles WHERE url = ? LIMIT 1",
            (url,),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def mark_article_processed(
    url: str,
    title: str = "",
    source: str = "",
    tweet_text: str = "",
) -> None:
    """
    Enregistre un article comme traité dans la base.

    :param url: URL canonique de l'article (clé unique)
    :param title: Titre de l'article
    :param source: Nom de la source RSS
    :param tweet_text: Texte du tweet généré / publié
    """
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT OR IGNORE INTO processed_articles
                (url, title, source, tweet_text, published_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (url, title, source, tweet_text, now, now),
        )
        conn.commit()
        logger.info("Article enregistré comme traité : %s", url)
    except sqlite3.IntegrityError as exc:
        logger.warning("Article déjà présent en base (ignoré) : %s — %s", url, exc)
    finally:
        conn.close()


def get_statistics() -> dict:
    """
    Retourne des statistiques simples sur la base.

    :return: dict avec count, last_processed_at
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) AS count, MAX(published_at) AS last FROM processed_articles"
        )
        row = cursor.fetchone()
        return {
            "count": row["count"] if row else 0,
            "last_processed_at": row["last"] if row else None,
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Breaking News — stockage et lecture
# ─────────────────────────────────────────────────────────────
def save_breaking_news(news: dict) -> None:
    """
    Enregistre une breaking news dans la base.

    :param news: dict avec title, url, source, summary, breaking_text, published_at, secondary_proposals
    """
    import json

    conn = get_connection()
    try:
        secondary = json.dumps(news.get("secondary_proposals", []), ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO breaking_news
                (title, url, source, summary, breaking_text, secondary_proposals, published_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                news.get("title", ""),
                news.get("url", ""),
                news.get("source", ""),
                news.get("summary", ""),
                news.get("breaking_text", ""),
                secondary,
                news.get("published_at", datetime.now(timezone.utc).isoformat()),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        logger.info("Breaking news enregistrée : %s", news.get("title", "")[:60])
    except sqlite3.IntegrityError as exc:
        logger.warning("Erreur d'enregistrement breaking news : %s", exc)
    finally:
        conn.close()


def get_latest_breaking_news() -> Optional[dict]:
    """
    Retourne la dernière breaking news stockée.

    :return: dict ou None si aucune news
    """
    import json

    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM breaking_news ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        # Désérialise les propositions secondaires
        if result.get("secondary_proposals"):
            try:
                result["secondary_proposals"] = json.loads(result["secondary_proposals"])
            except (json.JSONDecodeError, TypeError):
                result["secondary_proposals"] = []
        else:
            result["secondary_proposals"] = []
        return result
    finally:
        conn.close()


def clear_breaking_news_history() -> int:
    """
    Vide la table des breaking news.

    :return: Nombre de lignes supprimées
    """
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM breaking_news")
        conn.commit()
        removed = cursor.rowcount
        logger.info("Historique des breaking news vidé : %d lignes supprimées", removed)
        return removed
    finally:
        conn.close()


def clear_processed_articles() -> int:
    """
    Vide la table des articles traités (cache anti-doublons).

    :return: Nombre de lignes supprimées
    """
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM processed_articles")
        conn.commit()
        removed = cursor.rowcount
        logger.info("Articles traités vidés : %d lignes supprimées", removed)
        return removed
    finally:
        conn.close()


def get_breaking_news_history(limit: int = 50) -> list:
    """
    Retourne l'historique des breaking news (plus récentes d'abord).

    :param limit: Nombre maximum de news à retourner
    :return: Liste de dicts
    """
    import json

    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM breaking_news ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            if item.get("secondary_proposals"):
                try:
                    item["secondary_proposals"] = json.loads(item["secondary_proposals"])
                except (json.JSONDecodeError, TypeError):
                    item["secondary_proposals"] = []
            else:
                item["secondary_proposals"] = []
            result.append(item)
        return result
    finally:
        conn.close()
