"""
Script de publication immédiate — post groupé sur Facebook et Instagram.

Usage :
    python publish_now.py

Génère un post et le publie sur les 2 plateformes.
"""

import logging
import sys
from datetime import datetime, timezone

import config
import database
import news_service
from main import publish_news_facebook, publish_news_instagram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("publish-now")


def main() -> None:
    """Génère et publie un post sur les 2 plateformes (Facebook + Instagram)."""
    logger.info("🚀 Publication immédiate d'un post groupé Streetweb")
    logger.info("Heure serveur (UTC) : %s", datetime.now(timezone.utc).strftime("%H:%M:%S"))
    logger.info("Mode dry-run : %s", config.DRY_RUN)

    # 1. Initialisation de la base de données
    database.init_db()

    # 2. Génération du post
    logger.info("=== Génération du post ===")
    news = news_service.generate_breaking_news()
    if not news:
        logger.error("❌ Échec de la génération du post")
        sys.exit(1)

    logger.info("✅ Post généré : %s", news["title"][:80])
    logger.info("   Texte : %s", news["breaking_text"][:120])

    # 3. Publication sur Facebook et Instagram
    results = {}

    logger.info("── Publication sur Facebook ──")
    results["facebook"] = publish_news_facebook(news)

    logger.info("── Publication sur Instagram ──")
    results["instagram"] = publish_news_instagram(news)

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
