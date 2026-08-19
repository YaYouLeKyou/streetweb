"""
Service de Breaking News — scraping + génération + stockage.

Récupère les derniers articles Faits Divers & Culture Urbaine via RSS, sélectionne les 3
meilleurs articles, génère un résumé avec l'IA pour
chacun, et les stocke en base pour affichage sur la page web.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

import config
import database
import rss_parser
import ai_generator

logger = logging.getLogger(__name__)

# Nombre de propositions à générer (1 principale + 2 secondaires)
NUM_PROPOSALS = 3

# Verrou pour empêcher l'exécution concurrente de generate_breaking_news().
# Sans cela, un appel via /api/refresh peut se superposer à un job planifié,
# entraînant des scans RSS parallèles et des doublons dans la base.
_breaking_news_lock = threading.Lock()


def generate_breaking_news(force: bool = False) -> Optional[dict]:
    """
    Génère une breaking news à partir des derniers articles RSS.

    :param force: Si True, ignore le verrou anti-concurrence (utilisé par
                  l'API web /api/refresh et /api/post-now).
    :return: dict avec les infos de la news, ou None si échec
    """
    logger.info("=== Génération d'une breaking news ===")

    # Empêche l'exécution concurrente (superposition job planifié + API)
    if force:
        # En mode force (appel via l'interface web), on attend que le verrou
        # soit libéré — requête bloquante mais simple.
        _breaking_news_lock.acquire(blocking=True)
    else:
        # Sinon, si un job est déjà en cours, on échoue immédiatement.
        if not _breaking_news_lock.acquire(blocking=False):
            logger.warning(
                "Génération de breaking news déjà en cours — appel ignoré. "
                "Attendez que le cycle précédent se termine."
            )
            return None

    try:
        # 1. Récupération des nouveaux articles RSS (non encore traités)
        articles = rss_parser.fetch_new_articles(max_items=config.MAX_ARTICLES_TO_PROCESS)

        if not articles:
            logger.warning("Aucun nouvel article récupéré depuis les flux RSS.")
            return None

        # 2. Sélection des 3 meilleurs articles (les plus récents)
        best_articles = articles[:NUM_PROPOSALS]
        logger.info(
            "Articles sélectionnés : %d (le plus récent : « %s »)",
            len(best_articles),
            best_articles[0].title[:60],
        )

        # 3. Génération des résumés par l'IA pour chaque article
        proposals = []
        for i, article in enumerate(best_articles):
            breaking_text = ai_generator.generate_tweet(
                title=article.title,
                url=article.url,
                source=article.source,
                summary=article.summary,
            )

            if not breaking_text:
                logger.warning("Échec de la génération IA pour la proposition %d", i + 1)
                # Marque l'article comme traité pour ne pas bloquer indéfiniment
                database.mark_article_processed(
                    url=article.url,
                    title=article.title,
                    source=article.source,
                    tweet_text="",
                )
                continue

            proposals.append({
                "title": article.title,
                "url": article.url,
                "source": article.source,
                "summary": article.summary,
                "breaking_text": breaking_text,
                "image": article.image,
            })

        if not proposals:
            logger.error("Aucune proposition générée par l'IA.")
            return None

        # 4. Construction de l'objet news (principale + secondaires)
        now = datetime.now(timezone.utc).isoformat()
        news = {
            "title": proposals[0]["title"],
            "url": proposals[0]["url"],
            "source": proposals[0]["source"],
            "summary": proposals[0]["summary"],
            "breaking_text": proposals[0]["breaking_text"],
            "published_at": now,
            "secondary_proposals": proposals[1:],
            "image": proposals[0].get("image"),
        }

        # 5. Stockage en base
        database.save_breaking_news(news)

        # 6. Marque tous les articles traités comme "déjà publiés" (anti-doublons)
        for proposal in proposals:
            database.mark_article_processed(
                url=proposal["url"],
                title=proposal["title"],
                source=proposal["source"],
                tweet_text=proposal["breaking_text"],
            )

        logger.info(
            "Breaking news générée et stockée : %s (+ %d propositions secondaires)",
            news["title"][:60],
            len(news["secondary_proposals"]),
        )
        return news
    finally:
        _breaking_news_lock.release()


def generate_proposal() -> Optional[dict]:
    """
    Génère une seule proposition secondaire (article non traité).
    Utilisé par le bouton 🔄 des cartes "Autres propositions".

    :return: dict avec titre, url, source, summary, breaking_text, image, ou None
    """
    logger.info("=== Génération d'une proposition secondaire ===")

    # Empêche l'exécution concurrente avec un cycle complet
    if not _breaking_news_lock.acquire(blocking=False):
        logger.warning(
            "Génération de breaking news déjà en cours — appel ignoré. "
            "Attendez que le cycle précédent se termine."
        )
        return None

    try:
        # 1. Récupération des nouveaux articles RSS (non encore traités)
        articles = rss_parser.fetch_new_articles(max_items=config.MAX_ARTICLES_TO_PROCESS)

        if not articles:
            logger.warning("Aucun article disponible pour une proposition secondaire.")
            return None

        # 2. Sélection du premier article
        article = articles[0]

        # 3. Génération du texte par l'IA
        breaking_text = ai_generator.generate_tweet(
            title=article.title,
            url=article.url,
            source=article.source,
            summary=article.summary,
        )

        if not breaking_text:
            logger.warning("Échec de la génération IA pour la proposition secondaire")
            # Marque l'article comme traité pour ne pas bloquer indéfiniment
            database.mark_article_processed(
                url=article.url,
                title=article.title,
                source=article.source,
                tweet_text="",
            )
            return None

        proposal = {
            "title": article.title,
            "url": article.url,
            "source": article.source,
            "summary": article.summary,
            "breaking_text": breaking_text,
            "image": article.image,
        }

        # 4. Marque l'article comme traité (anti-doublons)
        database.mark_article_processed(
            url=article.url,
            title=article.title,
            source=article.source,
            tweet_text=breaking_text,
        )

        logger.info("Proposition secondaire générée : %s", article.title[:60])
        return proposal
    finally:
        _breaking_news_lock.release()


def get_latest_news() -> Optional[dict]:
    """Retourne la dernière breaking news stockée en base."""
    return database.get_latest_breaking_news()


def get_all_news(limit: int = 50) -> list:
    """Retourne l'historique des breaking news."""
    return database.get_breaking_news_history(limit=limit)
