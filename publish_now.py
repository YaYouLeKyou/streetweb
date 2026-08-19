"""
Script de publication immédiate — post groupé sur Facebook, Instagram et Twitter.

Usage :
    python publish_now.py

Génère une breaking news et la publie sur les 3 plateformes.
"""

import logging
import sys
from datetime import datetime, timezone

import config
import database
import news_service
from main import publish_news_tweet, publish_news_facebook, publish_news_instagram, publish_news_threads

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("publish-now")


def main() -> None:
    """Génère et publie une breaking news sur les 3 plateformes."""
    logger.info("🚀 Publication immédiate d'une breaking news groupée")
    logger.info("Heure serveur (UTC) : %s", datetime.now(timezone.utc).strftime("%H:%M:%S"))
    logger.info("Mode dry-run : %s", config.DRY_RUN)

    # 1. Initialisation de la base de données
    database.init_db()

    # 2. Génération de la breaking news
    logger.info("=== Génération de la breaking news ===")
    news = news_service.generate_breaking_news()
    if not news:
        logger.error("❌ Échec de la génération de la breaking news")
        sys.exit(1)

    logger.info("✅ Breaking news générée : %s", news["title"][:80])
    logger.info("   Texte : %s", news["breaking_text"][:120])

    # 3. Publication sur les 4 plateformes
    results = {}

    # Threads
    logger.info("── Publication sur Threads ──")
    results["threads"] = publish_news_threads(news)

    # Facebook
    logger.info("── Publication sur Facebook ──")
    results["facebook"] = publish_news_facebook(news)

    # Instagram
    logger.info("── Publication sur Instagram ──")
    results["instagram"] = publish_news_instagram(news)

    # Twitter
    logger.info("── Publication sur Twitter ──")
    results["twitter"] = publish_news_tweet(news)

    # 4. Résumé
    logger.info("=" * 60)
    logger.info("RÉSULTAT DE LA PUBLICATION GROUPÉE")
    logger.info("=" * 60)
    for platform, success in results.items():
        status = "✅ Publié" if success else "❌ Échec"
        logger.info("  %-10s : %s", platform.upper(), status)

    all_success = all(results.values())
    if all_success:
        logger.info("🎉 Toutes les publications ont réussi !")
    else:
        logger.warning("⚠️  Certaines publications ont échoué — voir les logs ci-dessus")
        sys.exit(1)


if __name__ == "__main__":
    main()