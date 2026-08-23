"""
Streetweb — Exécution unique d'un cycle de publication (GitHub Actions).
============================================================

Contrairement à main.py (worker longue durée avec scheduler),
ce script exécute UN SEUL cycle de génération + publication puis se termine.
Il est conçu pour être appelé par GitHub Actions à chaque créneau planifié :
la base SQLite anti-doublons est commitée dans le dépôt après chaque run
afin de persister entre les exécutions (les runners sont éphémères).
"""

import io
import logging
import sys

import config
import database

# Import du module principal (aucun effet de bord à l'import :
# la boucle infinie n'est lancée que via main.main())
import main

_utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=_utf8_stdout,
)
logger = logging.getLogger("streetweb-runonce")


def run() -> bool:
    """Exécute un cycle complet : init BDD → génération → publication."""
    logger.info("=== Cycle unique Streetweb (GitHub Actions) ===")
    logger.info("Mode dry-run : %s", config.DRY_RUN)

    # 1. Initialisation de la base de données (restaurée depuis le dépôt)
    database.init_db()
    stats = database.get_statistics()
    logger.info(
        "Base de donnees : %s (articles traites : %d)",
        config.DB_PATH,
        stats.get("count", 0),
    )

    # 2. Un seul cycle de génération + publication Facebook/Instagram
    success = main.generate_news_job()

    if success:
        logger.info("Cycle termine avec succes.")
    else:
        logger.error("Cycle termine en echec.")
    return success


if __name__ == "__main__":
    sys.exit(0 if run() else 1)