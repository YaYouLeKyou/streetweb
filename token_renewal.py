"""
Script de renouvellement automatique des tokens API (Facebook, Threads).

Vérifie la validité des tokens d'accès, les renouvelle si nécessaire,
et envoie une notification email en cas de token expiré ou invalide.

Fonctionnement :
  - Facebook : vérifie via /debug_token, renouvelle via fb_exchange_token
               (nécessite FB_APP_ID et FB_APP_SECRET dans la configuration)
  - Threads  : renouvelle via /refresh_access_token (reset à 60 jours)

Usage :
    python token_renewal.py              # Vérifie et renouvelle
    python token_renewal.py --check      # Vérification seule (sans renouvellement)
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone

import requests

import config
import email_notifier
from facebook_client import refresh_threads_token, DEBUG_TOKEN_URL, GRAPH_API_URL

logger = logging.getLogger("token-renewal")

# Fichier .env pour mise à jour locale des tokens
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# Seuil de renouvellement Facebook (jours avant expiration)
FB_RENEW_THRESHOLD_DAYS = 30


def check_facebook_token() -> dict:
    """
    Vérifie la validité du token Facebook via /debug_token.

    :return: dict avec :
        - valid: True si valide, False si invalide/expiré, None si erreur réseau
        - expires_at: timestamp d'expiration (si disponible)
        - days_left: jours restants avant expiration (si disponible)
        - error: message d'erreur (si applicable)
    """
    if not config.FB_PAGE_ACCESS_TOKEN:
        return {"valid": False, "error": "FB_PAGE_ACCESS_TOKEN manquant"}

    try:
        params = {
            "input_token": config.FB_PAGE_ACCESS_TOKEN,
            "access_token": config.FB_PAGE_ACCESS_TOKEN,
        }
        response = requests.get(DEBUG_TOKEN_URL, params=params, timeout=30)
        data = response.json()

        if response.status_code != 200:
            error = data.get("error", {})
            return {
                "valid": False,
                "error": error.get("message", str(data)),
            }

        token_info = data.get("data", {})
        is_valid = token_info.get("is_valid", False)

        expires_at = token_info.get("expires_at")
        days_left = None
        if expires_at:
            days_left = (expires_at - int(time.time())) / 86400

        return {
            "valid": is_valid,
            "expires_at": expires_at,
            "days_left": days_left,
            "type": token_info.get("type"),
            "scopes": token_info.get("scopes", []),
        }

    except requests.exceptions.RequestException as exc:
        logger.error("Erreur réseau lors de la vérification du token Facebook : %s", exc)
        return {"valid": None, "error": f"Erreur réseau : {exc}"}
    except Exception as exc:  # noqa: BLE001
        logger.error("Erreur inattendue lors de la vérification du token Facebook : %s", exc)
        return {"valid": None, "error": f"Erreur inattendue : {exc}"}


def refresh_facebook_token() -> str:
    """
    Rafraîchit le token Facebook via l'endpoint fb_exchange_token.

    Nécessite FB_APP_ID et FB_APP_SECRET dans la configuration.
    Renvoie le nouveau token, ou l'ancien en cas d'échec.
    """
    if not config.FB_APP_ID or not config.FB_APP_SECRET:
        logger.warning(
            "FB_APP_ID / FB_APP_SECRET manquants — "
            "impossible de rafraîchir le token Facebook"
        )
        return config.FB_PAGE_ACCESS_TOKEN

    params = {
        "grant_type": "fb_exchange_token",
        "client_id": config.FB_APP_ID,
        "client_secret": config.FB_APP_SECRET,
        "fb_exchange_token": config.FB_PAGE_ACCESS_TOKEN,
    }

    try:
        response = requests.get(
            f"{GRAPH_API_URL}/oauth/access_token",
            params=params,
            timeout=30,
        )
        data = response.json()

        if "access_token" in data:
            new_token = data["access_token"]
            logger.info("✅ Token Facebook rafraîchi avec succès")
            return new_token

        logger.error(
            "Erreur rafraîchissement token Facebook : %s",
            data.get("error", data),
        )
        return config.FB_PAGE_ACCESS_TOKEN

    except requests.exceptions.RequestException as exc:
        logger.error("Erreur réseau rafraîchissement token Facebook : %s", exc)
        return config.FB_PAGE_ACCESS_TOKEN
    except Exception as exc:  # noqa: BLE001
        logger.error("Exception rafraîchissement token Facebook : %s", exc)
        return config.FB_PAGE_ACCESS_TOKEN


def update_env_file(key: str, value: str) -> bool:
    """
    Met à jour une variable dans le fichier .env.

    :param key: Nom de la variable (ex: THREADS_ACCESS_TOKEN)
    :param value: Nouvelle valeur
    :return: True si la mise à jour a réussi
    """
    try:
        if not os.path.exists(ENV_FILE):
            logger.warning("Fichier .env introuvable — création")
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
        logger.error("Erreur mise à jour .env : %s", exc)
        return False


def renew_all_tokens(send_email: bool = True) -> dict:
    """
    Vérifie et renouvelle tous les tokens API.

    :param send_email: Si True, envoie des alertes email en cas de problème
    :return: dict avec les résultats par plateforme
    """
    results = {}

    # ── 1. Vérification du token Facebook ──
    logger.info("── Vérification du token Facebook ──")
    fb_info = check_facebook_token()

    if fb_info.get("valid") is False:
        logger.error("❌ Token Facebook INVALIDE ou EXPIRÉ")
        results["facebook"] = {"status": "expired", "info": fb_info}
        if send_email:
            email_notifier.send_token_expired_alert(
                platform="Facebook",
                token_name="FB_PAGE_ACCESS_TOKEN",
                error_detail=fb_info.get("error", "Token invalide ou expiré"),
            )
    elif fb_info.get("valid") is True:
        days_left = fb_info.get("days_left")
        if days_left is not None:
            logger.info("✅ Token Facebook valide — %.1f jours restants", days_left)
        else:
            logger.info("✅ Token Facebook valide (expiration inconnue)")

        # Renouvellement si le token expire bientôt
        if days_left is not None and days_left < FB_RENEW_THRESHOLD_DAYS:
            logger.info(
                "Token Facebook expire dans %.1f jours — renouvellement...",
                days_left,
            )
            new_token = refresh_facebook_token()
            if new_token != config.FB_PAGE_ACCESS_TOKEN:
                config.FB_PAGE_ACCESS_TOKEN = new_token
                update_env_file("FB_PAGE_ACCESS_TOKEN", new_token)
                results["facebook"] = {"status": "renewed"}
                if send_email:
                    email_notifier.send_generic_alert(
                        subject="✅ Token Facebook renouvelé avec succès",
                        body=(
                            "Le token Facebook a été renouvelé automatiquement.\n"
                            f"Date : {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}\n"
                            "Le nouveau token a été mis à jour dans .env.\n"
                            "⚠️ Si l'application tourne sur Render, mettez à jour "
                            "FB_PAGE_ACCESS_TOKEN dans le dashboard Render."
                        ),
                    )
            else:
                results["facebook"] = {"status": "renewal_failed"}
                logger.error("❌ Échec du renouvellement du token Facebook")
                if send_email:
                    email_notifier.send_token_expired_alert(
                        platform="Facebook",
                        token_name="FB_PAGE_ACCESS_TOKEN",
                        error_detail="Échec du renouvellement — token proche de l'expiration",
                    )
        else:
            results["facebook"] = {"status": "valid"}
    else:
        # Erreur réseau — on ne peut pas vérifier
        logger.warning("⚠️ Impossible de vérifier le token Facebook (erreur réseau)")
        results["facebook"] = {"status": "check_failed", "info": fb_info}

    # ── 2. Renouvellement du token Threads ──
    logger.info("── Renouvellement du token Threads ──")
    if not config.THREADS_ACCESS_TOKEN:
        logger.error("❌ THREADS_ACCESS_TOKEN manquant")
        results["threads"] = {"status": "missing"}
        if send_email:
            email_notifier.send_token_expired_alert(
                platform="Threads",
                token_name="THREADS_ACCESS_TOKEN",
                error_detail="THREADS_ACCESS_TOKEN non configuré",
            )
    else:
        # Le refresh Threads redonne 60 jours de validité
        logger.info("Appel à /refresh_access_token (reset à 60 jours)...")
        new_token = refresh_threads_token(config.THREADS_ACCESS_TOKEN)

        if new_token != config.THREADS_ACCESS_TOKEN:
            config.THREADS_ACCESS_TOKEN = new_token
            update_env_file("THREADS_ACCESS_TOKEN", new_token)
            results["threads"] = {"status": "renewed"}
            logger.info("✅ Token Threads renouvelé — 60 jours de validité")
            if send_email:
                email_notifier.send_generic_alert(
                    subject="✅ Token Threads renouvelé avec succès",
                    body=(
                        "Le token Threads a été renouvelé automatiquement.\n"
                        f"Date : {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}\n"
                        "Le nouveau token a été mis à jour dans .env.\n"
                        "⚠️ Si l'application tourne sur Render, mettez à jour "
                        "THREADS_ACCESS_TOKEN dans le dashboard Render."
                    ),
                )
        else:
            results["threads"] = {"status": "renewal_failed"}
            logger.error("❌ Échec du renouvellement du token Threads")
            if send_email:
                email_notifier.send_token_expired_alert(
                    platform="Threads",
                    token_name="THREADS_ACCESS_TOKEN",
                    error_detail="Échec du rafraîchissement — token peut-être expiré",
                )

    # ── 3. Résumé ──
    logger.info("=" * 60)
    logger.info("RÉSUMÉ DU RENOUVELLEMENT DES TOKENS")
    logger.info("=" * 60)
    for platform, result in results.items():
        status = result.get("status", "inconnu")
        logger.info("  %-10s : %s", platform.upper(), status)

    return results


def main() -> None:
    """Point d'entrée du script."""
    parser = argparse.ArgumentParser(
        description="Renouvellement automatique des tokens API (Facebook, Threads)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Vérification seule (sans renouvellement)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    logger.info("🚀 Démarrage du renouvellement automatique des tokens")
    logger.info("Heure : %s", datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"))

    if args.check:
        logger.info("Mode vérification seule — aucun renouvellement effectué")
        fb_info = check_facebook_token()
        if fb_info.get("valid") is True:
            days_left = fb_info.get("days_left")
            if days_left is not None:
                logger.info("✅ Token Facebook valide — %.1f jours restants", days_left)
            else:
                logger.info("✅ Token Facebook valide (expiration inconnue)")
        elif fb_info.get("valid") is False:
            logger.error("❌ Token Facebook invalide : %s", fb_info.get("error", "inconnu"))
            email_notifier.send_token_expired_alert(
                platform="Facebook",
                token_name="FB_PAGE_ACCESS_TOKEN",
                error_detail=fb_info.get("error", "Token invalide ou expiré"),
            )
        else:
            logger.warning("⚠️ Impossible de vérifier le token Facebook (erreur réseau)")
        return

    renew_all_tokens()


if __name__ == "__main__":
    main()