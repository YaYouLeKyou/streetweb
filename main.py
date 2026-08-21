"""
Streetweb — Veille Faits Divers & Culture Urbaine
====================================================

Orchestrateur principal :
  - Scan des flux RSS Faits Divers & Culture Urbaine
  - Génération d'un post sensationnaliste
  - Publication automatique sur Facebook + Instagram (Meta Graph API)
  - Affichage sur une page web (Flask)

Planification : 4 posts/jour (défaut 07:00, 12:00, 17:00, 20:00 heure de Paris)
Déploiement : Render / Railway Worker (`worker: python main.py`)
"""

import io
import logging
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import schedule

import config
import database
import email_notifier
import facebook_client
import news_service
import token_renewal
import web_app
from web_app import _build_long_post_message

# Import de la fonction utilitaire pour le fallback d'image Instagram
from facebook_client import get_valid_instagram_image

# Conversion heure de Paris ↔ UTC
from config import get_paris_tz, paris_time_to_utc, utc_time_to_paris

# ─────────────────────────────────────────────────────────────
# Journalisation (logs clairs formatés pour dashboard serveur)
# ─────────────────────────────────────────────────────────────
_utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=_utf8_stdout,
)
logger = logging.getLogger("streetweb-agent")

# Set mémoire des heures déjà rattrapées pendant la durée de vie du worker
_caught_up_times = set()


# ─────────────────────────────────────────────────────────────
# Publication d'un post sur Facebook
# ─────────────────────────────────────────────────────────────
def publish_news_facebook(news: dict) -> bool:
    """
    Publie le post généré sur la page Facebook (ou simule en dry-run).

    :param news: dict avec breaking_text, title, url
    :return: True si publié (ou simulé), False sinon
    """
    if not news or not news.get("breaking_text"):
        logger.warning("Aucun texte de post à publier sur Facebook")
        return False

    # Si Facebook n'est pas configuré, on log simplement
    if not config.FB_PAGE_ACCESS_TOKEN or not config.FACEBOOK_PAGE_ID:
        logger.warning(
            "Facebook non configuré — post non publié. "
            "Renseignez FB_PAGE_ACCESS_TOKEN et FACEBOOK_PAGE_ID dans .env"
        )
        return False

    try:
        facebook = facebook_client.FacebookClient()
        if not facebook.configure():
            logger.error("Échec de la configuration Facebook")
            # Envoi d'une alerte email si le token est expiré/invalide
            email_notifier.send_token_expired_alert(
                platform="Facebook",
                token_name="FB_PAGE_ACCESS_TOKEN",
                error_detail="Token Facebook invalide ou expiré (échec de configuration)",
            )
            return False

        message = _build_long_post_message(news)
        link = news.get("url", "")
        raw_image = news.get("image") or ""
        image_url = get_valid_instagram_image(
            caption=message,
            user_image_url=raw_image,
            title=news.get("title", ""),
        )
        long_text = news.get("long_text") or message
        published = facebook.post_to_page(message=long_text, link=link, image_url=image_url)
        if published:
            logger.info("Post Facebook publié : %s", news["title"][:60])
        else:
            logger.error("Echec de la publication du post Facebook")
            # Vérifie si l'échec est dû à un token expiré
            if facebook.is_token_expired_error():
                email_notifier.send_token_expired_alert(
                    platform="Facebook",
                    token_name="FB_PAGE_ACCESS_TOKEN",
                    error_detail=facebook.last_error_message,
                )
        return published

    except Exception as exc:  # noqa: BLE001
        logger.error("Erreur lors de la publication Facebook : %s", exc)
        return False


# ─────────────────────────────────────────────────────────────
# Publication d'un post sur Instagram
# ─────────────────────────────────────────────────────────────
def publish_news_instagram(news: dict) -> bool:
    """
    Publie le post généré sur Instagram (ou simule en dry-run).

    :param news: dict avec breaking_text, title, url, image
    :return: True si publié (ou simulé), False sinon
    """
    if not news or not news.get("breaking_text"):
        logger.warning("Aucun texte de post à publier sur Instagram")
        return False

    if not config.FB_PAGE_ACCESS_TOKEN or not config.INSTAGRAM_ACCOUNT_ID:
        logger.warning(
            "Instagram non configuré — post non publié. "
            "Renseignez FB_PAGE_ACCESS_TOKEN et INSTAGRAM_ACCOUNT_ID dans .env"
        )
        return False

    try:
        facebook = facebook_client.FacebookClient()
        if not facebook.configure():
            logger.error("Echec de la configuration Facebook/Instagram")
            # Envoi d'une alerte email si le token est expiré/invalide
            email_notifier.send_token_expired_alert(
                platform="Instagram",
                token_name="FB_PAGE_ACCESS_TOKEN",
                error_detail="Token Facebook/Instagram invalide ou expiré (échec de configuration)",
            )
            return False

        message = _build_long_post_message(news)
        image_url = get_valid_instagram_image(
            caption=message,
            user_image_url=news.get("image") or "",
            title=news.get("title", ""),
        )
        long_text = news.get("long_text") or message
        published = facebook.post_to_instagram(message=long_text, image_url=image_url)
        if published:
            logger.info("Post Instagram publié : %s", news["title"][:60])
        else:
            logger.error("Echec de la publication du post Instagram")
            # Vérifie si l'échec est dû à un token expiré
            if facebook.is_token_expired_error():
                email_notifier.send_token_expired_alert(
                    platform="Instagram",
                    token_name="FB_PAGE_ACCESS_TOKEN",
                    error_detail=facebook.last_error_message,
                )
        return published

    except Exception as exc:  # noqa: BLE001
        logger.error("Erreur lors de la publication Instagram : %s", exc)
        return False


# ─────────────────────────────────────────────────────────────
# Génération + publication d'un post
# ─────────────────────────────────────────────────────────────
def generate_news_job() -> bool:
    """Génère un nouveau post et le publie sur Facebook + Instagram."""
    logger.info("=== Génération planifiée d'un post ===")
    news = news_service.generate_breaking_news()
    if news:
        logger.info("Post genere : %s", news["title"][:60])
        logger.info("Envoi du post aux API Facebook/Instagram...")
        # Publication Facebook
        try:
            facebook_success = publish_news_facebook(news)
            logger.info("Publication Facebook %s", "réussie" if facebook_success else "échouée")
            if not facebook_success:
                logger.error("Échec de la publication Facebook")
        except Exception as exc:
            logger.error("Erreur lors de la publication Facebook : %s", exc)
            return False

        # Publication Instagram
        try:
            instagram_success = publish_news_instagram(news)
            logger.info("Publication Instagram %s", "réussie" if instagram_success else "échouée")
            if not instagram_success:
                logger.error("Échec de la publication Instagram")
        except Exception as exc:
            logger.error("Erreur lors de la publication Instagram : %s", exc)
            return False

        if facebook_success and instagram_success:
            logger.info("Cycle de publication terminé avec succès.")
        else:
            logger.warning("Cycle de publication terminé avec échec partiel.")
        return facebook_success and instagram_success
    else:
        logger.warning("Echec de la generation du post")
        return False


# ─────────────────────────────────────────────────────────────
# Renouvellement automatique des tokens API
# ─────────────────────────────────────────────────────────────
def renew_tokens_job() -> None:
    """
    Vérifie et renouvelle les tokens Facebook.
    Planifié tous les TOKEN_RENEWAL_DAYS jours (défaut : 30).
    Envoie une notification email si un token est expiré ou invalide.
    """
    logger.info("=== Renouvellement automatique des tokens API ===")
    try:
        results = token_renewal.renew_all_tokens(send_email=True)
        for platform, result in results.items():
            status = result.get("status", "inconnu")
            logger.info("  %-10s : %s", platform.upper(), status)
    except Exception as exc:  # noqa: BLE001
        logger.error("Erreur lors du renouvellement des tokens : %s", exc)
        email_notifier.send_generic_alert(
            subject="⚠️ Erreur lors du renouvellement automatique des tokens",
            body=(
                "Une erreur est survenue lors du renouvellement automatique des tokens.\n"
                f"Erreur : {exc}\n"
                f"Date : {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}"
            ),
        )


# ─────────────────────────────────────────────────────────────
# Planification avec `schedule`
# ─────────────────────────────────────────────────────────────
_schedule_lock = threading.Lock()


def _clear_schedule() -> None:
    """Supprime tous les jobs planifiés (thread-safe)."""
    with _schedule_lock:
        schedule.clear()


def setup_schedule() -> None:
    """Planifie la génération des posts aux heures configurées."""
    with _schedule_lock:
        schedule_times = config.SCHEDULE_TIMES
        interval = config.NEWS_INTERVAL_HOURS

        if interval > 0 and interval is not None:
            schedule.every(interval).hours.do(generate_news_job)
            logger.info("Post planifié : toutes les %d heures", interval)
        else:
            for time_str in schedule_times:
                # Les heures de la config sont TOUJOURS en heure de Paris.
                # Conversion explicite Paris → UTC : le worker Render/Railway
                # tourne en UTC, et on évite ainsi toute dépendance au
                # paramètre `tz` de la librairie `schedule` (source de bugs).
                # La conversion gère automatiquement l'heure d'été (UTC+2)
                # et l'heure d'hiver (UTC+1).
                utc_time = paris_time_to_utc(time_str)
                schedule.every().day.at(utc_time).do(generate_news_job)
                logger.info(
                    "Post planifié : %s (heure Paris = %s UTC)",
                    time_str,
                    utc_time,
                )

            if not schedule_times:
                # Protection contre schedule.every(0).hours (heure locale invalide).
                # Si NEWS_INTERVAL_HOURS=0 et aucune heure fixe, on utilise 6h.
                default_interval = interval if interval > 0 else 6
                schedule.every(default_interval).hours.do(generate_news_job)
                logger.info("Post planifié : toutes les %d heures", default_interval)

        # Renouvellement automatique des tokens API
        # Tous les TOKEN_RENEWAL_DAYS jours (défaut : 30) — les tokens Meta
        # durent 60 jours, ce renouvellement garantit qu'ils ne expirent jamais.
        renewal_days = config.TOKEN_RENEWAL_DAYS
        if renewal_days > 0:
            schedule.every(renewal_days).days.do(renew_tokens_job)
            logger.info(
                "Renouvellement des tokens API planifié : tous les %d jours",
                renewal_days,
            )
        else:
            logger.warning(
                "Renouvellement automatique des tokens désactivé (TOKEN_RENEWAL_DAYS=%d)",
                renewal_days,
            )


def reschedule_global() -> None:
    """
    Re-planifie l'ensemble des publications à partir de la config courante.
    Utilisé par l'interface web quand l'utilisateur change les heures
    ou la fréquence depuis le dashboard.
    """
    _clear_schedule()
    setup_schedule()
    logger.info("Planification globale mise à jour")


def _catch_up_missed_posts(schedule_times: list) -> bool:
    """
    Vérifie si des publications planifiées ont été manquées au démarrage
    ou lors d'un réveil du worker (ex : plan gratuit Render qui s'endort
    après 15 min d'inactivité).

    RATTRAPE TOUS LES POSTS MANQUÉS (pas seulement un seul).
    Ne retente pas deux fois la même heure planifiée.

    :return: True si au moins un post de rattrapage a été exécuté, False sinon
    """
    if not schedule_times or config.NEWS_INTERVAL_HOURS > 0:
        return False

    # Les heures sont en heure de Paris — nous devons comparer en heure de Paris
    paris_tz = get_paris_tz()
    now = datetime.now(paris_tz)  # heure de Paris
    current_time = now.strftime("%H:%M")

    caught_up = 0
    # Vérifie chaque heure planifiée (ordonnée pour un rattrapage logique)
    for scheduled_time in sorted(schedule_times):
        if scheduled_time in _caught_up_times:
            continue
        # Si l'heure planifiée (Paris) est passée
        if current_time >= scheduled_time:
            logger.info(
                "Post planifie a %s (heure de Paris) manque — rattrapage en cours",
                scheduled_time,
            )
            try:
                if generate_news_job():
                    _caught_up_times.add(scheduled_time)
                    caught_up += 1
                    logger.info("Rattrapage reussi — post manque a %s publie", scheduled_time)
                else:
                    logger.warning("Rattrapage ignoré — génération du post échouée pour %s", scheduled_time)
            except Exception as exc:  # noqa: BLE001
                logger.error("Erreur lors du post de rattrapage : %s", exc)
                _caught_up_times.add(scheduled_time)
                break

    if caught_up:
        reschedule_global()
    else:
        logger.info("Aucun post manque — tous les posts planifies ont ete publies")
    return caught_up > 0


# ─────────────────────────────────────────────────────────────
# Lancement du serveur web en arrière-plan
# ─────────────────────────────────────────────────────────────
def start_web_server() -> None:
    """Démarre le serveur web Flask dans un thread séparé."""
    web_port = int(config.WEB_PORT)
    web_thread = threading.Thread(
        target=web_app.run_web_server,
        kwargs={"host": "0.0.0.0", "port": web_port},
        daemon=True,
    )
    web_thread.start()
    logger.info("Serveur web demarre sur le port %d", web_port)


# ─────────────────────────────────────────────────────────────
# Point d'entrée principal
# ─────────────────────────────────────────────────────────────
def _generate_initial_news() -> None:
    """Génère le premier post en arrière-plan (thread séparé)."""
    try:
        if config.TEST_ON_STARTUP:
            logger.info("TEST_ON_STARTUP=true — exécution immédiate d'un cycle complet")
            generate_news_job()
        else:
            # Génération immédiate d'un premier post (avec publication)
            logger.info("Génération du premier post et publication...")
            generate_news_job()
    except Exception as exc:  # noqa: BLE001
        logger.error("Erreur lors de la génération initiale : %s", exc)


def _check_tokens_on_startup() -> None:
    """
    Vérifie la validité des tokens API au démarrage (thread séparé).
    Envoie une notification email si un token est expiré ou invalide.
    """
    logger.info("Vérification des tokens API au démarrage…")
    try:
        results = token_renewal.renew_all_tokens(send_email=True)
        for platform, result in results.items():
            status = result.get("status", "inconnu")
            logger.info("  %-10s : %s", platform.upper(), status)
    except Exception as exc:  # noqa: BLE001
        logger.error("Erreur lors de la vérification des tokens au démarrage : %s", exc)


def main() -> None:
    """Boucle principale : planification + publication + serveur web."""
    logger.info("Demarrage de Streetweb — Veille Faits Divers & Culture Urbaine")
    logger.info("Heure serveur (UTC) : %s", datetime.now(timezone.utc).strftime("%H:%M:%S"))
    logger.info("Mode dry-run : %s", config.DRY_RUN)

    # 1. Initialisation de la base de données
    database.init_db()
    stats = database.get_statistics()
    logger.info("Base de donnees : %s (articles traites : %d)", config.DB_PATH, stats.get("count", 0))

    # 2. Planification des posts
    reschedule_global()

    # 2bis. Rattrapage des posts manqués au démarrage
    _catch_up_missed_posts(config.SCHEDULE_TIMES)

    # 3. Lancement du serveur web IMMÉDIATEMENT (avant la génération initiale)
    start_web_server()

    # 4. Génération initiale en arrière-plan (thread séparé)
    #    Le serveur web est déjà accessible pendant le scan des flux RSS
    initial_thread = threading.Thread(target=_generate_initial_news, daemon=True)
    initial_thread.start()

    # 4bis. Vérification des tokens API au démarrage (thread séparé)
    #    Envoie une notification email si un token est expiré ou invalide
    token_check_thread = threading.Thread(target=_check_tokens_on_startup, daemon=True)
    token_check_thread.start()

    # 5. Boucle infinie du worker
    logger.info("Boucle de planification active (Ctrl+C pour arreter)…")
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur — bye!")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        logger.critical("Erreur fatale dans la boucle principale : %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
