"""Service de Breaking News optimisé - Version 2026"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, List

import config
import database
import rss_parser
import ai_generator

logger = logging.getLogger(__name__)
_breaking_news_lock = threading.Lock()


def generate_breaking_news() -> Optional[Dict]:
    """Génère une breaking news à partir des derniers articles RSS."""
    logger.info("=== Génération d'une breaking news ===")

    if not _breaking_news_lock.acquire(blocking=False):
        logger.warning("Génération déjà en cours - ignorez la requête non forcée")
        return None

    try:
        articles = rss_parser.fetch_new_articles(max_items=config.MAX_ARTICLES_TO_PROCESS)
        if not articles:
            logger.warning("Aucun nouvel article RSS trouvé")
            return None

        selected_article = articles[0]
        logger.info("Article sélectionné : %s", selected_article.title[:60])

        complete_post = ai_generator.generate_complete_post(
            title=selected_article.title,
            url=selected_article.url,
            source=selected_article.source,
            summary=selected_article.summary
        )

        if not complete_post:
            logger.error("Échec IA - article marqué comme traité")
            database.mark_article_processed(url=selected_article.url)
            return None

        current_time = datetime.now(timezone.utc).isoformat()
        news = {
            "title": complete_post.get("title", selected_article.title[:100]),
            "url": selected_article.url,
            "source": selected_article.source,
            "summary": selected_article.summary,
            "breaking_text": complete_post.get("body", f"{selected_article.title} {selected_article.url} #FaitsDivers"),
            "long_text": complete_post.get("long_body", complete_post.get("body", "")),
            "published_at": current_time,
            "image": selected_article.image
        }

        logger.info("Génération terminée - sauvegarde en base")

        database.save_breaking_news(news)

        # Marque uniquement le post principal comme traité (pas de propositions secondaires inutiles)
        database.mark_article_processed(
            url=selected_article.url,
            title=selected_article.title,
            source=selected_article.source,
            post_text=complete_post.get("body", f"{selected_article.title} {selected_article.url} #FaitsDivers")
        )

        return news
    finally:
        _breaking_news_lock.release()


def generate_proposal() -> Optional[Dict]:
    """Génère une proposition secondaire non utilisée"""
    if not _breaking_news_lock.acquire(blocking=False):
        return None

    try:
        articles = rss_parser.fetch_new_articles(max_items=config.MAX_ARTICLES_TO_PROCESS)
        if not articles:
            return None

        article = articles[0]
        breaking_text = ai_generator.generate_post(
            title=article.title,
            url=article.url,
            source=article.source,
            summary=article.summary
        )

        if not breaking_text:
            return None

        return {
            "title": article.title,
            "url": article.url,
            "source": article.source,
            "summary": article.summary,
            "breaking_text": breaking_text,
            "image": article.image
        }
    finally:
        _breaking_news_lock.release()


def get_latest_news(limit: int = 10) -> Optional[Dict]:
    """Récupère la dernière breaking news stockée en base."""
    return database.get_latest_breaking_news()


def get_all_news(limit: int = 50) -> List:
    """Retourne l'historique des breaking news."""
    return database.get_breaking_news_history(limit=limit)