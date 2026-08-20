"""
Application Web — Affichage des Posts Streetweb.

Sert une page web qui affiche le dernier post généré
par le scraper, avec :
  - Choix de la fréquence de mise à jour (2h, 4h, 8h... 48h)
  - Bouton "Post Now" pour publier en direct
  - Simulation visuelle du post pour validation
"""

import logging
import os
import re
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

import config
import database
import email_notifier
import facebook_client
import news_service

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Fichier .env pour persistance des réglages modifiés via le dashboard
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _update_env_var(key: str, value: str) -> bool:
    """Met à jour une variable dans le fichier .env (persistance)."""
    try:
        if not os.path.exists(ENV_FILE):
            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.write(f"{key}={value}\n")
            return True

        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        found = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break

        if not found:
            lines.append(f"{key}={value}\n")

        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)

        logger.info("✅ %s mis à jour dans .env", key)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Erreur mise à jour .env (%s) : %s", key, exc)
        return False

# Fréquences disponibles (en heures)
# 0 = désactivé (publication uniquement aux heures planifiées)
AVAILABLE_INTERVALS = [0, 2, 4, 6, 8, 12, 24, 48]


def _format_date(iso_str: str) -> str:
    """Convertit une date ISO (UTC) en format lisible en heure de Paris."""
    if not iso_str:
        return ""
    try:
        from zoneinfo import ZoneInfo

        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        paris_dt = dt.astimezone(ZoneInfo(config.LOCAL_TIMEZONE))
        return paris_dt.strftime("%d/%m/%Y à %H:%M")
    except (ValueError, TypeError):
        return iso_str


@app.route("/")
def index():
    """Page principale : affiche le dernier post + historique."""
    latest = news_service.get_latest_news()
    history = news_service.get_all_news(limit=20)

    # Formatage des dates pour l'affichage
    if latest:
        latest["published_at_display"] = _format_date(latest.get("published_at", ""))
    for item in history:
        item["published_at_display"] = _format_date(item.get("published_at", ""))

    stats = database.get_statistics()
    current_interval = config.NEWS_INTERVAL_HOURS
    schedule_times = config.SCHEDULE_TIMES

    # Vérifie si les réseaux sont configurés
    facebook_configured = bool(config.FB_PAGE_ACCESS_TOKEN and config.FACEBOOK_PAGE_ID)
    instagram_configured = bool(config.FB_PAGE_ACCESS_TOKEN and config.INSTAGRAM_ACCOUNT_ID)

    from zoneinfo import ZoneInfo
    paris_now = datetime.now(ZoneInfo(config.LOCAL_TIMEZONE))
    return render_template(
        "index.html",
        latest=latest,
        history=history,
        stats=stats,
        now=paris_now.strftime("%d/%m/%Y %H:%M (heure de Paris)"),
        paris_timezone=config.LOCAL_TIMEZONE,
        available_intervals=AVAILABLE_INTERVALS,
        current_interval=current_interval,
        schedule_times=schedule_times,
        facebook_configured=facebook_configured,
        instagram_configured=instagram_configured,
        dry_run=config.DRY_RUN,
        test_on_startup=config.TEST_ON_STARTUP,
        max_history_size=config.MAX_HISTORY_SIZE,
    )


@app.route("/ping")
def ping():
    """
    Endpoint de réveil — utilisé par un cron externe (cron-job.org, UptimeRobot)
    pour réveiller le worker Render (plan gratuit) et exécuter les posts planifiés.

    Exécute schedule.run_pending() et le rattrapage des posts manqués,
    puis retourne "pong".
    """
    try:
        import schedule as schedule_module
        import main as main_module

        schedule_module.run_pending()
        main_module._catch_up_missed_posts(config.SCHEDULE_TIMES)
    except Exception as exc:  # noqa: BLE001
        logger.error("Erreur lors du traitement /ping : %s", exc)

    return "pong", 200


@app.route("/api/latest")
def api_latest():
    """API JSON : dernier post."""
    latest = news_service.get_latest_news()
    if not latest:
        return jsonify({"error": "Aucun post disponible"}), 404
    return jsonify(latest)


@app.route("/api/history")
def api_history():
    """API JSON : historique des posts."""
    history = news_service.get_all_news(limit=50)
    return jsonify(history)


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """
    API JSON : force la génération d'un nouveau post.
    Filtre les articles déjà traités pour toujours renvoyer du contenu neuf.
    """
    news = news_service.generate_breaking_news(force=True)
    if not news:
        latest = news_service.get_latest_news()
        if latest:
            return jsonify({
                "success": False,
                "error": "Aucun nouvel article disponible.",
                "message": "Tous les articles RSS ont déjà été publiés. "
                           "Patientez jusqu'à de nouveaux articles, ou "
                           "effacez l'historique pour tout republier.",
                "latest_title": latest["title"][:50],
            }), 409
        return jsonify({
            "error": "Échec de la génération d'article.",
            "detail": "Tous les flux RSS ont été épuisés ou inaccessible.",
        }), 404
    return jsonify(news)


@app.route("/api/refresh-proposal")
def api_refresh_proposal():
    """
    API JSON : génère une seule proposition secondaire (article non traité).
    Utilisé par le bouton 🔄 des cartes "Autres propositions".
    """
    proposal = news_service.generate_proposal()
    if not proposal:
        latest = news_service.get_latest_news()
        if latest:
            return jsonify({
                "success": False,
                "error": "Aucun nouvel article disponible.",
                "message": "Tous les articles RSS ont déjà été publiés. "
                           "Patientez jusqu'à de nouveaux articles, ou "
                           "effacez l'historique pour tout republier.",
                "latest_title": latest["title"][:50],
            }), 409
        return jsonify({
            "error": "Échec de la génération de la proposition.",
            "detail": "Tous les flux RSS ont été épuisés ou inaccessible.",
        }), 404
    return jsonify(proposal)


@app.route("/api/clear-history", methods=["POST"])
def api_clear_history():
    """API : vide l'historique des posts et le cache anti-doublons."""
    removed_news = database.clear_breaking_news_history()
    removed_processed = database.clear_processed_articles()
    logger.info(
        "Historique vidé : %d posts, %d articles traités supprimés",
        removed_news,
        removed_processed,
    )
    return jsonify({
        "success": True,
        "message": "Historique effacé avec succès.",
        "removed_news": removed_news,
        "removed_processed": removed_processed,
    })


@app.route("/api/interval", methods=["POST"])
def api_set_interval():
    """API : change la fréquence de mise à jour (en heures). 0 = désactivé."""
    data = request.get_json(silent=True) or {}
    try:
        interval = int(data.get("interval", 2))
    except (ValueError, TypeError):
        return jsonify({"error": "Intervalle invalide"}), 400

    if interval not in AVAILABLE_INTERVALS:
        return jsonify({"error": f"Intervalle non autorisée. Choisissez parmi : {AVAILABLE_INTERVALS}"}), 400

    config.NEWS_INTERVAL_HOURS = interval
    logger.info("Fréquence de mise à jour changée : %s", "désactivée" if interval == 0 else f"toutes les {interval} heures")

    # Persistance dans .env pour que la fréquence survive au redémarrage
    _update_env_var("NEWS_INTERVAL_HOURS", str(interval))

    import main as main_module
    main_module.reschedule_global()

    return jsonify({"success": True, "interval": interval, "label": "Désactivé" if interval == 0 else f"Toutes les {interval} heures"})


@app.route("/api/schedule", methods=["POST"])
def api_set_schedule():
    """
    API : change les heures de publication planifiées (format HH:MM, heure de Paris).
    Re-planifie immédiatement les publications.
    """
    data = request.get_json(silent=True) or {}
    raw_times = data.get("times", [])

    # Validation du format HH:MM
    valid_times = []
    for t in raw_times:
        t = str(t).strip()
        if re.match(r"^([01]\d|2[0-3]):[0-5]\d$", t):
            valid_times.append(t)

    if not valid_times:
        return jsonify({
            "error": "Aucune heure valide. Format attendu : HH:MM (ex: 08:30, 17:30)",
        }), 400

    # Mise à jour de la configuration et re-planification
    config.SCHEDULE_TIMES = valid_times

    # Persistance dans .env pour que les heures survivent au redémarrage
    # du worker Render (plan gratuit : redémarrages fréquents)
    _update_env_var("SCHEDULE_TIMES", ",".join(valid_times))

    import main as main_module
    main_module.reschedule_global()

    logger.info("Heures de publication mises à jour : %s (heure de Paris)", valid_times)
    return jsonify({"success": True, "times": valid_times, "timezone": config.LOCAL_TIMEZONE})


def _build_long_post_message(news: dict) -> str:
    title = (news.get("title") or "").strip()
    summary = (news.get("summary") or "").strip()
    url = (news.get("url") or "").strip()

    parts = []
    if title:
        parts.append(title)
    if summary:
        parts.append(summary)
    if url:
        parts.append(url)

    message = "\n\n".join(parts)
    return message.strip()


@app.route("/api/post-now", methods=["POST"])
def api_post_now():
    """
    API : génère un nouveau post et le publie sur les
    plateformes sélectionnées : facebook, instagram.
    Retourne la simulation visuelle et le statut de publication.
    """
    data = request.get_json(silent=True) or {}
    raw_network = data.get("network", "facebook")
    if isinstance(raw_network, str):
        networks = [n.strip() for n in raw_network.split(",") if n.strip()]
    else:
        networks = [str(raw_network)]

    valid_networks = [n for n in networks if n in ("facebook", "instagram")]
    if not valid_networks:
        valid_networks = ["facebook"]

    post_facebook = "facebook" in valid_networks
    post_instagram = "instagram" in valid_networks

    progress = []
    result = {
        "success": True,
        "network": ",".join(valid_networks),
        "progress": progress,
    }

    # 1. Génération du post
    news = news_service.generate_breaking_news(force=True)
    if not news:
        latest = news_service.get_latest_news()
        if latest:
            return jsonify({
                "error": "Article déjà publié récemment.",
                "detail": "Le dernier post a déjà été publié. Patientez jusqu'à de nouveaux articles RSS.",
                "latest_title": latest["title"][:50],
            }), 409
        return jsonify({"error": "Aucun article disponible."}), 404

    progress.append({"step": "generation", "message": "Article généré avec succès", "done": True})

    # 2. Simulation visuelle du post
    post_preview = {
        "text": news["breaking_text"],
        "title": news["title"],
        "url": news["url"],
        "source": news["source"],
        "published_at": news["published_at"],
        "character_count": len(news["breaking_text"]),
    }
    result["post_preview"] = post_preview
    result["news"] = news

    # 3. Publication sur Facebook (seulement si explicitement demandé)
    facebook_published = False
    facebook_error = None
    if post_facebook:
        progress.append({"step": "facebook", "message": "Envoi du post Facebook…", "done": False})
        if not config.DRY_RUN and config.FB_PAGE_ACCESS_TOKEN and config.FACEBOOK_PAGE_ID:
            try:
                facebook = facebook_client.FacebookClient()
                if facebook.configure():
                    facebook_message = news.get("long_text") or _build_long_post_message(news)
                    raw_image = news.get("image") or ""
                    facebook_image = facebook_client.get_valid_instagram_image(
                        caption=news["breaking_text"],
                        user_image_url=raw_image,
                        title=news.get("title", ""),
                    )
                    facebook_published = facebook.post_to_page(
                        message=facebook_message,
                        link=news.get("url", ""),
                        image_url=facebook_image,
                    )
                    logger.info("Post Facebook publié : %s", facebook_published)
                    progress[-1]["done"] = True
                    progress[-1]["success"] = facebook_published
                    if not facebook_published:
                        facebook_error = "Échec de la publication Facebook — voir les logs serveur"
                        progress[-1]["error"] = facebook_error
                else:
                    facebook_error = (
                        "Token Facebook/Instagram expiré ou invalide. "
                        "Générez un nouveau Page Access Token sur "
                        "https://developers.facebook.com/tools/access-token/ "
                        "avec les permissions pages_read_engagement et pages_manage_posts, "
                        "puis redémarrez l'application."
                    )
                    progress[-1]["done"] = True
                    progress[-1]["success"] = False
                    progress[-1]["error"] = facebook_error
                    # Notification email en cas de token expiré
                    email_notifier.send_token_expired_alert(
                        platform="Facebook",
                        token_name="FB_PAGE_ACCESS_TOKEN",
                        error_detail=facebook_error,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.error("Erreur lors de la publication Facebook : %s", exc)
                facebook_error = str(exc)
                progress[-1]["done"] = True
                progress[-1]["success"] = False
                progress[-1]["error"] = facebook_error
        else:
            progress[-1]["done"] = True
            progress[-1]["success"] = False
            if config.DRY_RUN:
                progress[-1]["error"] = "Mode dry-run activé"
            elif not config.FB_PAGE_ACCESS_TOKEN or not config.FACEBOOK_PAGE_ID:
                progress[-1]["error"] = "Facebook non configuré"
    else:
        progress.append({"step": "facebook", "message": "Facebook non sélectionné", "done": True, "skipped": True})

    result["facebook_published"] = facebook_published
    result["facebook_error"] = facebook_error

    # 4. Publication sur Instagram (seulement si explicitement demandé)
    instagram_published = False
    instagram_error = None
    if post_instagram:
        progress.append({"step": "instagram", "message": "Envoi du post Instagram…", "done": False})
        if not config.DRY_RUN and config.FB_PAGE_ACCESS_TOKEN and config.INSTAGRAM_ACCOUNT_ID:
            try:
                facebook = facebook_client.FacebookClient()
                if facebook.configure():
                    instagram_image = facebook_client.get_valid_instagram_image(
                        caption=news["breaking_text"],
                        user_image_url=news.get("image"),
                        title=news.get("title", ""),
                    )
                    instagram_message = news.get("long_text") or _build_long_post_message(news)
                    instagram_published = facebook.post_to_instagram(
                        message=instagram_message,
                        image_url=instagram_image,
                    )
                    logger.info("Post Instagram publié : %s", instagram_published)
                    progress[-1]["done"] = True
                    progress[-1]["success"] = instagram_published
                    if not instagram_published:
                        instagram_error = "Échec de la publication Instagram — voir les logs serveur"
                        progress[-1]["error"] = instagram_error
                else:
                    instagram_error = (
                        "Token Instagram expiré ou invalide. "
                        "Générez un nouveau Page Access Token sur "
                        "https://developers.facebook.com/tools/access-token/ "
                        "avec les permissions pages_read_engagement et pages_manage_posts, "
                        "puis redémarrez l'application."
                    )
                    progress[-1]["done"] = True
                    progress[-1]["success"] = False
                    progress[-1]["error"] = instagram_error
                    # Notification email en cas de token expiré
                    email_notifier.send_token_expired_alert(
                        platform="Instagram",
                        token_name="FB_PAGE_ACCESS_TOKEN",
                        error_detail=instagram_error,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.error("Erreur lors de la publication Instagram : %s", exc)
                instagram_error = str(exc)
                progress[-1]["done"] = True
                progress[-1]["success"] = False
                progress[-1]["error"] = instagram_error
        else:
            progress[-1]["done"] = True
            progress[-1]["success"] = False
            if config.DRY_RUN:
                progress[-1]["error"] = "Mode dry-run activé"
            elif not config.INSTAGRAM_ACCOUNT_ID:
                progress[-1]["error"] = "Instagram non configuré"
    else:
        progress.append({"step": "instagram", "message": "Instagram non sélectionné", "done": True, "skipped": True})

    result["instagram_published"] = instagram_published
    result["instagram_error"] = instagram_error
    result["dry_run"] = config.DRY_RUN

    # Message final de progression
    if post_facebook or post_instagram:
        has_success = (post_facebook and facebook_published) or (post_instagram and instagram_published)
        if has_success:
            progress.append({"step": "done", "message": "Publication terminée avec succès !", "done": True, "final": True})
        else:
            progress.append({"step": "done", "message": "Publication terminée (partielle)", "done": True, "final": True})
    else:
        progress.append({"step": "done", "message": "Publication échouée", "done": True, "final": True, "error": True})

    return jsonify(result)


@app.route("/api/facebook/status")
def api_facebook_status():
    """API : vérifie si Facebook est configuré."""
    configured = bool(config.FB_PAGE_ACCESS_TOKEN and config.FACEBOOK_PAGE_ID)
    return jsonify({
        "configured": configured,
        "dry_run": config.DRY_RUN,
    })


@app.route("/api/facebook/connect", methods=["POST"])
def api_facebook_connect():
    """
    API : vérifie la connexion Facebook en testant la configuration.
    Retourne l'état de la connexion et les infos de la page.
    """
    if not config.FB_PAGE_ACCESS_TOKEN or not config.FACEBOOK_PAGE_ID:
        return jsonify({
            "success": False,
            "error": "Facebook n'est pas configuré. Renseignez FB_PAGE_ACCESS_TOKEN et FACEBOOK_PAGE_ID dans .env",
        }), 400

    try:
        facebook = facebook_client.FacebookClient()
        if facebook.configure(verify_token=True):
            page_info = facebook.get_page_info()
            return jsonify({
                "success": True,
                "message": "Connexion Facebook établie avec succès",
                "page_name": page_info.get("name") if page_info else None,
                "page_fans": page_info.get("fan_count") if page_info else None,
                "dry_run": config.DRY_RUN,
            })
        return jsonify({
            "success": False,
            "error": "Token Facebook invalide ou expiré (code 190/467). "
                     "Générez un nouveau Page Access Token sur "
                     "https://developers.facebook.com/tools/access-token/ "
                     "avec les permissions pages_read_engagement et pages_manage_posts.",
        }), 400
    except Exception as exc:  # noqa: BLE001
        logger.error("Erreur lors de la connexion Facebook : %s", exc)
        return jsonify({
            "success": False,
            "error": f"Erreur lors de la connexion Facebook : {exc}",
        }), 500


@app.route("/api/facebook/diagnostic")
def api_facebook_diagnostic():
    """
    API : diagnostic complet du token Facebook.
    Vérifie la validité du token et les permissions via /debug_token.
    """
    if not config.FB_PAGE_ACCESS_TOKEN:
        return jsonify({
            "success": False,
            "error": "FB_PAGE_ACCESS_TOKEN non configuré dans .env",
        }), 400

    facebook = facebook_client.FacebookClient()
    token_info = facebook.check_token()

    if token_info is None:
        return jsonify({
            "success": False,
            "error": "Erreur réseau lors de la vérification du token Meta",
        }), 500

    return jsonify({
        "success": True,
        "token_info": token_info,
        "page_id": config.FACEBOOK_PAGE_ID,
        "dry_run": config.DRY_RUN,
    })


def run_web_server(host: str = "0.0.0.0", port: int = 5000) -> None:
    """Lance le serveur web Flask."""
    logger.info("Serveur web demarre sur http://%s:%d", host, port)
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    database.init_db()
    run_web_server()
