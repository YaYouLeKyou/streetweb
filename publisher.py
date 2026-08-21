#!/usr/bin/env python3
"""
Module de publication résiliente — Gestion centralisée des publications Facebook et Instagram.

Ce module assure :
1. Gestion d'images OBLIGATOIRE et PERTINENTE (RSS → Unsplash → Fallback)
2. Mode fallback "Sans IA" 100% résilient
3. Publication systématique sur les deux plateformes
4. Gestion des erreurs et logging détaillé
5. Validation des configurations avant publication
"""

import logging
import os
import threading
import time
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timezone

import requests
import config
import database
import facebook_client
from facebook_client import get_valid_instagram_image

logger = logging.getLogger(__name__)

# Verrou pour éviter les publications concurrentes
_publication_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────
# Récupération flexible des identifiants Facebook / Instagram
# Plusieurs alias de noms de variables d'environnement sont
# acceptés afin qu'aucune publication ne soit bloquée si le nom
# varie légèrement entre l'environnement local (.env) et Render.
# ─────────────────────────────────────────────────────────────
def _get_fb_token() -> str:
    """Récupération flexible du token Facebook (alias supportés)."""
    return (
        config.FB_PAGE_ACCESS_TOKEN
        or os.getenv("FB_PAGE_ACCESS_TOKEN")
        or os.getenv("FACEBOOK_ACCESS_TOKEN")
        or os.getenv("FB_ACCESS_TOKEN")
        or os.getenv("META_ACCESS_TOKEN")
        or ""
    )


def _get_fb_page_id() -> str:
    """Récupération flexible de l'ID de Page (avec repli sur l'ID valide)."""
    return (
        config.FACEBOOK_PAGE_ID
        or os.getenv("FACEBOOK_PAGE_ID")
        or os.getenv("FB_PAGE_ID")
        or "277418232940596"
    )


def _get_ig_account_id() -> str:
    """Récupération flexible de l'ID de compte Instagram (alias supportés)."""
    return (
        config.INSTAGRAM_ACCOUNT_ID
        or os.getenv("INSTAGRAM_ACCOUNT_ID")
        or os.getenv("IG_USER_ID")
        or ""
    )

class ImageManager:
    """Gestionnaire d'images résilient avec fallback automatique."""

    @staticmethod
    def _validate_image_url(image_url: str) -> bool:
        """Valide qu'une URL d'image est accessible et valide."""
        if not image_url or not image_url.startswith("http"):
            return False

        try:
            response = requests.head(
                image_url,
                timeout=10,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "").lower()
                return content_type.startswith("image/")
        except requests.RequestException:
            return False

        return False

    @staticmethod
    def _get_unsplash_image(keywords: str) -> Optional[str]:
        """Récupère une image depuis Unsplash basée sur des mots-clés."""
        try:
            # Utilisation de l'API Unsplash (nécessite une clé API dans .env)
            unsplash_access_key = config.UNSPLASH_ACCESS_KEY
            if not unsplash_access_key:
                logger.warning("UNSPLASH_ACCESS_KEY non configuré — fallback vers image par défaut")
                return None

            # Construction de la requête
            query = f"street culture, {keywords}, urban news"
            url = f"https://api.unsplash.com/photos/random?query={query}&orientation=landscape&client_id={unsplash_access_key}"

            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                data = response.json()
                return data.get("urls", {}).get("regular")

            logger.warning("Échec de la récupération Unsplash (code %d)", response.status_code)
            return None
        except Exception as exc:
            logger.error("Erreur Unsplash : %s", exc)
            return None

    @staticmethod
    def _get_fallback_image() -> str:
        """Retourne une image de fallback thématique."""
        # Images de fallback thématiques (culture urbaine / street)
        fallback_images = [
            "https://images.unsplash.com/photo-1493225255756-d9584f8606e9?w=1080&h=1080&fit=crop",
            "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=1080&h=1080&fit=crop",
            "https://images.unsplash.com/photo-1501386761578-eac5c94b800a?w=1080&h=1080&fit=crop",
            "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=1080&h=1080&fit=crop",
            "https://images.unsplash.com/photo-1524293233570-2ec0e8c2d177?w=1080&h=1080&fit=crop",
        ]
        return fallback_images[datetime.now().minute % len(fallback_images)]

    @staticmethod
    def get_validated_image(news: Dict[str, Any]) -> str:
        """
        Retourne une URL d'image VALIDE pour publication Instagram/Facebook.
        Stratégie de fallback : RSS → Unsplash → Fallback thématique.
        """
        # 1. Essayer l'image RSS d'origine
        rss_image = news.get("image")
        if rss_image and ImageManager._validate_image_url(rss_image):
            logger.info("✅ Image RSS valide utilisée : %s", rss_image)
            return rss_image

        # 2. Générer une image via Unsplash si des mots-clés sont disponibles
        title = news.get("title", "")
        summary = news.get("summary", "")
        keywords = f"{title} {summary}".strip()[:100]

        if keywords:
            unsplash_image = ImageManager._get_unsplash_image(keywords)
            if unsplash_image and ImageManager._validate_image_url(unsplash_image):
                logger.info("✅ Image Unsplash générée : %s", unsplash_image)
                return unsplash_image

        # 3. Fallback thématique
        fallback_image = ImageManager._get_fallback_image()
        logger.info("⚠️  Image de fallback utilisée : %s", fallback_image)
        return fallback_image

class FallbackPostGenerator:
    """Générateur de posts en mode dégradé (sans IA)."""

    @staticmethod
    def generate_fallback_post(news: Dict[str, Any]) -> Dict[str, Any]:
        """
        Génère un post complet en mode dégradé sans appel LLM.
        Utilisé quand Gemini/IA est indisponible.
        """
        title = news.get("title", "Actualité urbaine")
        url = news.get("url", "")
        summary = news.get("summary", "")
        source = news.get("source", "Source inconnue")

        # Construction du post court (pour Instagram)
        body = f"{title}\n\n{summary}\n\n{url} #FaitsDivers #CultureUrbaine #Street"

        # Construction du post long (pour Facebook)
        long_body = f"{title}\n\n{summary}\n\nLire l'article complet : {url}\n\n#FaitsDivers #CultureUrbaine #Street"

        # Limitation de longueur
        max_length = config.MAX_POST_LENGTH
        if len(body) > max_length:
            body = body[:max_length-3] + "..."
        if len(long_body) > max_length:
            long_body = long_body[:max_length-3] + "..."

        return {
            "title": title,
            "body": body,
            "long_body": long_body,
            "fallback_mode": True,
            "source": source,
            "url": url
        }

class ResilientPublisher:
    """Publieur résilient avec gestion d'erreurs et fallback automatique."""

    @staticmethod
    def _validate_config() -> Tuple[bool, bool]:
        """Valide la configuration Facebook/Instagram (avec alias d'environnement)."""
        fb_token = _get_fb_token()
        fb_configured = bool(fb_token and _get_fb_page_id())
        ig_configured = bool(fb_token and _get_ig_account_id())
        return fb_configured, ig_configured

    @staticmethod
    def _publish_to_facebook(news: Dict[str, Any], image_url: str) -> bool:
        """Publie sur Facebook avec gestion d'erreurs."""
        try:
            facebook = facebook_client.FacebookClient()
            if not facebook.configure():
                logger.error("❌ Configuration Facebook échouée")
                return False

            message = news.get("long_text") or news.get("breaking_text")
            if not message:
                logger.error("❌ Message Facebook vide")
                return False

            success = facebook.post_to_page(
                message=message,
                link=news.get("url", ""),
                image_url=image_url
            )

            if success:
                logger.info("✅ Publication Facebook réussie")
                return True
            else:
                logger.error("❌ Publication Facebook échouée")
                return False

        except Exception as exc:
            logger.error("❌ Erreur publication Facebook : %s", exc)
            return False

    @staticmethod
    def _publish_to_instagram(news: Dict[str, Any], image_url: str) -> bool:
        """Publie sur Instagram avec gestion d'erreurs."""
        if not _get_ig_account_id():
            logger.warning("⚠️  Instagram non configuré (INSTAGRAM_ACCOUNT_ID manquant)")
            return False

        try:
            facebook = facebook_client.FacebookClient()
            if not facebook.configure():
                logger.error("❌ Configuration Instagram échouée")
                return False

            message = news.get("breaking_text") or news.get("long_text")
            if not message:
                logger.error("❌ Message Instagram vide")
                return False

            success = facebook.post_to_instagram(
                message=message,
                image_url=image_url
            )

            if success:
                logger.info("✅ Publication Instagram réussie")
                return True
            else:
                logger.error("❌ Publication Instagram échouée")
                return False

        except Exception as exc:
            logger.error("❌ Erreur publication Instagram : %s", exc)
            return False

    @staticmethod
    def publish_news(news: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        """
        Publie une news sur Facebook et Instagram avec gestion d'erreurs complète.
        Retourne toujours un dictionnaire avec le statut de chaque plateforme.
        """
        if not force:
            # Empêche les publications concurrentes
            if not _publication_lock.acquire(blocking=False):
                logger.warning("Publication déjà en cours — appel ignoré")
                return {
                    "success": False,
                    "error": "Publication déjà en cours",
                    "facebook": False,
                    "instagram": False
                }

        try:
            logger.info("=== Lancement de la publication résiliente ===")

            # 1. Validation de la configuration
            fb_configured, ig_configured = ResilientPublisher._validate_config()
            if not fb_configured:
                logger.error("❌ Facebook non configuré")
                return {
                    "success": False,
                    "error": "Facebook non configuré",
                    "facebook": False,
                    "instagram": False
                }

            # 2. Gestion d'image OBLIGATOIRE
            image_url = ImageManager.get_validated_image(news)
            if not image_url:
                logger.error("❌ Impossible de trouver une image valide")
                return {
                    "success": False,
                    "error": "Aucune image valide disponible",
                    "facebook": False,
                    "instagram": False
                }

            # 3. Publication Facebook
            fb_success = False
            if fb_configured:
                fb_success = ResilientPublisher._publish_to_facebook(news, image_url)
                time.sleep(2)  # Évite les problèmes de rate limiting

            # 4. Publication Instagram
            ig_success = False
            if ig_configured:
                ig_success = ResilientPublisher._publish_to_instagram(news, image_url)

            # 5. Résultat global
            success = fb_success or ig_success
            status = "✅ SUCCÈS" if success else "❌ ÉCHEC TOTAL"

            logger.info("=== Publication terminée : %s ===", status)
            logger.info("  - Facebook : %s", "✅ Réussi" if fb_success else "❌ Échoué")
            logger.info("  - Instagram : %s", "✅ Réussi" if ig_success else "❌ Échoué")

            return {
                "success": success,
                "facebook": fb_success,
                "instagram": ig_success,
                "image_used": image_url,
                "news_title": news.get("title", "")[:50]
            }

        finally:
            if not force:
                _publication_lock.release()

def publish_news_async(news: Dict[str, Any]) -> threading.Thread:
    """
    Lance la publication dans un thread séparé pour éviter de bloquer l'interface web.
    Retourne l'objet Thread pour suivi éventuel.
    """
    def publication_task():
        try:
            result = ResilientPublisher.publish_news(news, force=True)
            logger.info("Publication asynchrone terminée : %s", result)
        except Exception as exc:
            logger.error("Erreur dans la publication asynchrone : %s", exc)

    thread = threading.Thread(target=publication_task, daemon=True)
    thread.start()
    return thread

# Fonctions utilitaires pour l'intégration avec le code existant
def publish_news_facebook(news: Dict[str, Any]) -> bool:
    """Wrapper pour compatibilité avec main.py - Publication Facebook seule."""
    result = ResilientPublisher.publish_news(news)
    return result.get("facebook", False)

def publish_news_instagram(news: Dict[str, Any]) -> bool:
    """Wrapper pour compatibilité avec main.py - Publication Instagram seule."""
    result = ResilientPublisher.publish_news(news)
    return result.get("instagram", False)

def publish_news_both(news: Dict[str, Any]) -> bool:
    """Wrapper pour compatibilité avec main.py - Publication sur les deux plateformes."""
    result = ResilientPublisher.publish_news(news)
    return result.get("success", False)

if __name__ == "__main__":
    # Test unitaire
    test_news = {
        "title": "Test de publication résiliente",
        "url": "https://example.com/test",
        "summary": "Ceci est un test du système de publication résiliente.",
        "source": "Test Source",
        "breaking_text": "Test post avec hashtags #Test #Resilient #Street",
        "long_text": "Test post long avec plus de détails et hashtags #Test #Resilient #Street",
        "image": "https://example.com/invalid-image.jpg"
    }

    print("Test du publieur résilient...")
    result = ResilientPublisher.publish_news(test_news)
    print("Résultat :", result)