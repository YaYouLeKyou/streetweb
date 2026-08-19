"""
Module de notification par email — alerte en cas de token expiré.

Envoie un email à l'adresse configurée (ALERT_EMAIL) quand un token
d'accès API est détecté comme expiré ou invalide.

Utilise smtplib (bibliothèque standard Python) — aucun package requis.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

import config

logger = logging.getLogger(__name__)


def send_token_expired_alert(platform: str, token_name: str, error_detail: str = "") -> bool:
    """
    Envoie un email d'alerte indiquant qu'un token est expiré ou invalide.

    :param platform: Nom de la plateforme concernée (ex: "Facebook", "Instagram", "Threads")
    :param token_name: Nom de la variable de token (ex: "FB_PAGE_ACCESS_TOKEN")
    :param error_detail: Détail de l'erreur renvoyée par l'API (optionnel)
    :return: True si l'email a été envoyé, False sinon
    """
    if not config.SMTP_ENABLED:
        logger.warning("Notification email désactivée (SMTP_ENABLED=false)")
        return False

    if not config.ALERT_EMAIL:
        logger.warning("ALERT_EMAIL non configuré — impossible d'envoyer la notification")
        return False

    subject = f"⚠️ ALERTE : Token {platform} expiré ou invalide"
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    body = f"""
Bonjour,

Le token d'accès API pour la plateforme **{platform}** est expiré ou invalide.

Détails :
────────────
• Plateforme    : {platform}
• Variable      : {token_name}
• Date/heure    : {now_str}
"""

    if error_detail:
        body += f"• Erreur API     : {error_detail}\n"

    body += """
Action requise :
────────────
1. Générez un nouveau token sur le portail développeur de la plateforme.
2. Mettez à jour la variable d'environnement correspondante dans Render.
3. Redémarrez l'application.

Cordialement,
Votre bot de publication automatique
"""

    return _send_email(subject, body)


def send_generic_alert(subject: str, body: str) -> bool:
    """
    Envoie un email d'alerte générique.

    :param subject: Sujet de l'email
    :param body: Corps de l'email (texte brut)
    :return: True si l'email a été envoyé, False sinon
    """
    if not config.SMTP_ENABLED:
        logger.warning("Notification email désactivée (SMTP_ENABLED=false)")
        return False

    if not config.ALERT_EMAIL:
        logger.warning("ALERT_EMAIL non configuré — impossible d'envoyer la notification")
        return False

    return _send_email(subject, body)


def _send_email(subject: str, body: str) -> bool:
    """
    Envoie un email via SMTP.

    :param subject: Sujet de l'email
    :param body: Corps de l'email (texte brut)
    :return: True si l'email a été envoyé, False sinon
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config.SMTP_FROM_EMAIL
        msg["To"] = config.ALERT_EMAIL

        # Version texte brut
        text_part = MIMEText(body, "plain", "utf-8")
        msg.attach(text_part)

        # Version HTML (plus lisible)
        html_body = body.replace("\n", "<br>")
        html_part = MIMEText(f"<html><body>{html_body}</body></html>", "html", "utf-8")
        msg.attach(html_part)

        # Connexion SMTP
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30)
        server.ehlo()

        if config.SMTP_TLS:
            server.starttls()
            server.ehlo()

        if config.SMTP_USERNAME and config.SMTP_PASSWORD:
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)

        server.sendmail(config.SMTP_FROM_EMAIL, [config.ALERT_EMAIL], msg.as_string())
        server.quit()

        logger.info("✅ Email d'alerte envoyé à %s — sujet : %s", config.ALERT_EMAIL, subject)
        return True

    except smtplib.SMTPAuthenticationError as exc:
        logger.error("Erreur d'authentification SMTP : %s", exc)
        return False
    except smtplib.SMTPException as exc:
        logger.error("Erreur SMTP lors de l'envoi de l'email : %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.error("Erreur inattendue lors de l'envoi de l'email : %s", exc)
        return False