"""
Client Facebook / Meta pour publication et diagnostics.

Usage :
    from facebook_client import FacebookClient

    fb = FacebookClient()
    fb.configure()
    fb.post_to_page(message="Hello")
    fb.post_to_instagram(message="Hello Instagram")
    fb.post_to_threads(message="Hello Threads")
"""

import io
import json
import logging
import random
import time
import urllib.parse
from datetime import datetime
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

GRAPH_API_URL = "https://graph.facebook.com/v19.0"
DEBUG_TOKEN_URL = "https://graph.facebook.com/v19.0/debug_token"
THREADS_API_URL = "https://graph.threads.net/v1.0"
THREADS_REFRESH_URL = "https://graph.threads.net/refresh_access_token"

# Cache de validation token — évite des appels réseau répétés à /debug_token
_TOKEN_CACHE: dict = {}
_CACHE_TTL = 120

# Pool d'images de fallback pour Instagram (culture urbaine / street)
_FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1493225255756-d9584f8606e9?w=1080&h=1080&fit=crop",
    "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=1080&h=1080&fit=crop",
    "https://images.unsplash.com/photo-1501386761578-eac5c94b800a?w=1080&h=1080&fit=crop",
    "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=1080&h=1080&fit=crop",
    "https://images.unsplash.com/photo-1524293233570-2ec0e8c2d177?w=1080&h=1080&fit=crop",
    "https://images.unsplash.com/photo-1506157786151-b8491531f063?w=1080&h=1080&fit=crop",
    "https://images.unsplash.com/photo-1493225255756-d9584f8606e9?w=1080&h=1080&fit=crop",
    "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=1080&h=1080&fit=crop",
]


def refresh_threads_token(current_token: str) -> str:
    """
    Régénère le token Threads pour lui redonner 60 jours de validité.
    Renvoie le nouveau token s'il a été rafraîchi, ou l'ancien en cas d'erreur.
    """
    params = {
        "grant_type": "th_refresh_token",
        "access_token": current_token,
    }

    try:
        response = requests.get(THREADS_REFRESH_URL, params=params, timeout=10)
        data = response.json()

        if "access_token" in data:
            new_token = data["access_token"]
            logger.info("Token Threads rafraîchi avec succès pour 60 jours supplémentaires.")
            return new_token

        logger.error(
            "Erreur lors du rafraîchissement du token Threads : %s",
            data.get("error", data),
        )
        return current_token

    except Exception as exc:  # noqa: BLE001
        logger.error("Exception lors du rafraîchissement du token Threads : %s", exc)
        return current_token

def _generate_pollinations_image(prompt: str) -> str:
    """
    Génère une image via Pollinations.ai à partir d'un prompt texte.
    Retourne l'URL de l'image générée (endpoint image directe).
    """
    try:
        encoded_prompt = requests.utils.quote(prompt)
        image_url = f"https://image.pollinations.ai/p/{encoded_prompt}?width=1080&height=1080&model=flux&nologo=true"
        logger.info("Image générée via Pollinations : %s", image_url)
        return image_url
    except Exception as exc:  # noqa: BLE001
        logger.error("Erreur lors de la génération Pollinations : %s", exc)
        return ""


def get_valid_instagram_image(caption: str, user_image_url: str = None, title: str = "") -> str:
    """
    Retourne une URL d'image valide et accessible publiquement par l'API Instagram.

    1. Si une URL d'image valide est fournie (ex: image de l'article RSS), elle est utilisée.
    2. Sinon, une image est générée via Pollinations.ai en fonction du titre/texte.
    3. Si la génération échoue, une image de fallback thématique est utilisée.
    """
    if user_image_url and user_image_url.startswith("http"):
        try:
            res = requests.head(user_image_url, timeout=10, allow_redirects=True)
            if res.status_code == 200 and res.headers.get("content-type", "").startswith("image/"):
                logger.info("Utilisation de l'image RSS : %s", user_image_url)
                return user_image_url
        except requests.RequestException:
            logger.warning("L'URL d'image RSS n'est pas accessible. Génération d'une image contextualisée...")

    # Génération d'image contextualisée via Pollinations.ai
    if title or caption:
        prompt = title or caption
        prompt = prompt.strip()[:200]
        prompt = f"Streetweb faits divers culture urbaine, {prompt}, photo realiste, journalisme urbain"
        generated_url = _generate_pollinations_image(prompt)
        if generated_url:
            try:
                img_response = requests.head(generated_url, timeout=15, allow_redirects=True)
                if img_response.status_code == 200 and img_response.headers.get("content-type", "").startswith("image/"):
                    logger.info("Utilisation de l'image générée Pollinations : %s", generated_url)
                    return generated_url
            except requests.RequestException:
                logger.warning("L'image Pollinations générée n'est pas directement accessible. Fallback thématique.")

    fallback_image = random.choice(_FALLBACK_IMAGES)
    logger.info("Utilisation de l'image de fallback thématique : %s", fallback_image)
    return fallback_image


class FacebookClient:
    """Client pour l'API Facebook / Meta."""

    # Codes d'erreur Meta indiquant un token expiré/invalide
    TOKEN_EXPIRED_CODES = {190, 467, 10, 200}

    def __init__(self) -> None:
        self._is_configured = False
        self._token_type = "unknown"
        self.last_error_message = ""
        self._last_error_code = None

    def is_token_expired_error(self) -> bool:
        """
        Vérifie si la dernière erreur rencontrée est due à un token expiré ou invalide.

        :return: True si l'erreur est liée à un token expiré/invalide
        """
        if self._last_error_code is None:
            return False
        return self._last_error_code in self.TOKEN_EXPIRED_CODES

    def _record_error(self, data: dict) -> None:
        """
        Enregistre le message et le code d'erreur de la dernière réponse API.

        :param data: Réponse JSON de l'API Meta
        """
        error = data.get("error", {}) if isinstance(data, dict) else {}
        self.last_error_message = error.get("message", "")
        self._last_error_code = error.get("code")
        if self._last_error_code in self.TOKEN_EXPIRED_CODES:
            logger.error(
                "⚠️  TOKEN EXPIRÉ OU INVALIDE détecté (code %s) : %s",
                self._last_error_code,
                self.last_error_message,
            )

    def configure(self, verify_token: bool = True) -> bool:
        """
        Configure le client avec les paramètres de config.py.

        :param verify_token: Si True, valide le token via /debug_token
        :return: True si la configuration est valide
        """
        if not config.FB_PAGE_ACCESS_TOKEN:
            logger.error("FB_PAGE_ACCESS_TOKEN manquant")
            return False

        if not config.FACEBOOK_PAGE_ID:
            logger.error("FACEBOOK_PAGE_ID manquant")
            return False

        self._is_configured = True

        if verify_token:
            token_info = self.check_token()
            if not token_info or not token_info.get("is_valid"):
                logger.error("Token Facebook invalide ou expiré")
                self._is_configured = False
                return False

        logger.info("Client Facebook configuré avec succès")
        return True

    def _post_with_retry(self, url: str, params: dict, max_retries: int = 3) -> Optional[requests.Response]:
        """
        Effectue une requête POST avec retry en cas d'erreur réseau.

        :param url: URL de la requête
        :param params: Paramètres de la requête
        :param max_retries: Nombre maximum de tentatives
        :return: Response object ou None en cas d'échec
        """
        for attempt in range(max_retries):
            try:
                response = requests.post(url, data=params, timeout=30)

                # Retry sur erreurs serveur 5xx
                if response.status_code >= 500 and attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(
                        "Erreur serveur %d, nouvelle tentative dans %ds...",
                        response.status_code, wait_time
                    )
                    time.sleep(wait_time)
                    continue

                return response

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning("Timeout, nouvelle tentative dans %ds...", wait_time)
                    time.sleep(wait_time)
                else:
                    logger.error("Timeout après %d tentatives", max_retries)
                    return None

            except requests.exceptions.RequestException as exc:
                logger.error("Erreur réseau : %s", exc)
                return None

        return None

    def check_token(self) -> Optional[dict]:
        """
        Vérifie la validité du token via /debug_token.

        :return: dict avec les infos du token, ou None si erreur
        """
        now = time.time()
        if _TOKEN_CACHE and (now - _TOKEN_CACHE.get("ts", 0)) < _CACHE_TTL:
            logger.debug("Token valide (cache)")
            return _TOKEN_CACHE["data"]

        if not config.FB_PAGE_ACCESS_TOKEN:
            logger.error("FB_PAGE_ACCESS_TOKEN manquant")
            return None

        try:
            params = {
                "input_token": config.FB_PAGE_ACCESS_TOKEN,
                "access_token": config.FB_PAGE_ACCESS_TOKEN,
            }
            response = requests.get(DEBUG_TOKEN_URL, params=params, timeout=30)
            data = response.json()

            if response.status_code != 200:
                logger.error("Erreur /debug_token : %s", data)
                return None

            token_info = data.get("data", {})
            is_valid = token_info.get("is_valid", False)

            if is_valid:
                _TOKEN_CACHE["ts"] = now
                _TOKEN_CACHE["data"] = token_info
                logger.info("Token valide : type=%s", token_info.get("type"))
            else:
                logger.error("Token invalide : %s", token_info)

            return token_info

        except requests.exceptions.RequestException as exc:
            logger.error("Erreur réseau lors de la vérification du token : %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error("Erreur inattendue lors de la vérification du token : %s", exc)
            return None

    def get_page_info(self) -> Optional[dict]:
        """
        Récupère les informations de la page Facebook.

        :return: dict avec les infos de la page, ou None si erreur
        """
        if not self._is_configured:
            logger.error("Client Facebook non configuré — appelez configure() d'abord")
            return None

        try:
            url = f"{GRAPH_API_URL}/{config.FACEBOOK_PAGE_ID}"
            params = {
                "access_token": config.FB_PAGE_ACCESS_TOKEN,
                "fields": "id,name,about,fan_count,link",
            }
            response = requests.get(url, params=params, timeout=30)
            data = response.json()

            if response.status_code == 200:
                logger.info("Page Facebook récupérée : %s", data.get("name", "inconnue"))
                return data

            logger.error("Erreur Facebook API (get_page_info) : %s", data)
            return None

        except requests.RequestException as exc:
            logger.error("Erreur réseau lors de la récupération de la page : %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error("Erreur inattendue (get_page_info) : %s", exc)
            return None

    def _upload_photo(self, image_url: str) -> Optional[str]:
        """
        Upload une image sur la page Facebook et retourne son ID.

        Télécharge l'image puis l'upload via multipart/form-data
        pour éviter les erreurs de fetch par Facebook.

        :param image_url: URL publique de l'image à uploader
        :return: ID de la photo uploadée, ou None si échec
        """
        try:
            upload_url = f"{GRAPH_API_URL}/{config.FACEBOOK_PAGE_ID}/photos"

            # 1. Téléchargement de l'image
            image_bytes = None
            try:
                img_response = requests.get(image_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
                if img_response.status_code == 200 and img_response.headers.get("content-type", "").startswith("image/"):
                    image_bytes = img_response.content
            except requests.RequestException as exc:
                logger.warning("Impossible de télécharger l'image %s : %s", image_url, exc)

            # 2. Upload sur Facebook
            if image_bytes:
                files = {"source": ("image.jpg", io.BytesIO(image_bytes), "image/jpeg")}
                params = {
                    "access_token": config.FB_PAGE_ACCESS_TOKEN,
                    "published": "false",
                }
                response = requests.post(upload_url, params=params, files=files, timeout=30)
            else:
                params = {
                    "access_token": config.FB_PAGE_ACCESS_TOKEN,
                    "url": image_url,
                    "published": "false",
                }
                response = requests.post(upload_url, data=params, timeout=30)

            data = response.json()

            if response.status_code == 200 and data.get("id"):
                photo_id = data["id"]
                logger.info("Image uploadée sur Facebook — ID : %s", photo_id)
                return photo_id

            logger.error(
                "Erreur upload image Facebook (%d) : %s",
                response.status_code,
                data,
            )
            return None

        except requests.RequestException as exc:
            logger.error("Erreur réseau lors de l'upload de l'image Facebook : %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error("Erreur inattendue lors de l'upload de l'image Facebook : %s", exc)
            return None

    def post_to_page(self, message: str, link: str = "", image_url: str = "") -> bool:
        """
        Publie un post sur la page Facebook.

        :param message: Contenu du post
        :param link: Lien à joindre au post (optionnel)
        :return: True si publié (ou simulé), False en cas d'échec
        """
        if not message:
            logger.error("Message vide — impossible de publier")
            return False

        if config.DRY_RUN:
            print("\n" + "=" * 60)
            print("MODE TEST (DRY RUN) — POST FACEBOOK NON ENVOYÉ")
            print("=" * 60)
            print(f"Page ID : {config.FACEBOOK_PAGE_ID}")
            print(f"Message : {message}")
            if link:
                print(f"Lien    : {link}")
            print("=" * 60 + "\n")
            logger.info("Dry-run : post Facebook affiché dans la console")
            return True

        if not self._is_configured:
            logger.error("Client Facebook non configuré — appelez configure() d'abord")
            return False

        try:
            photo_id = None

            if image_url:
                photo_id = self._upload_photo(image_url)
                if not photo_id:
                    logger.warning("Échec de l'upload de l'image — publication sans image")

            params = {
                "access_token": config.FB_PAGE_ACCESS_TOKEN,
                "message": message,
            }
            if link:
                params["link"] = link
            if photo_id:
                params["attached_media"] = json.dumps([{"media_fbid": photo_id}])

            url = f"{GRAPH_API_URL}/{config.FACEBOOK_PAGE_ID}/feed"
            logger.debug(
                "Envoi du post Facebook : POST %s | paramètres: %s | message (%d caractères)",
                url,
                {k: ("***" if k == "access_token" else v) for k, v in params.items()},
                len(message),
            )
            response = self._post_with_retry(url, params)
            data = response.json() if response is not None else {}

            logger.debug(
                "Réponse Facebook (%d) : %s",
                response.status_code if response is not None else -1,
                str(data)[:500],
            )

            if response is not None and response.status_code == 200 and data.get("id"):
                post_id = data["id"]
                logger.info("Post Facebook publié avec succès — ID : %s", post_id)
                return True

            self._record_error(data)
            error = data.get("error", {})
            logger.error(
                "Erreur Facebook API (%d) : code=%s type=%s message=%s | page_id=%s | token_type=%s",
                response.status_code if response is not None else -1,
                error.get("code"),
                error.get("type"),
                error.get("message"),
                config.FACEBOOK_PAGE_ID,
                self._token_type if hasattr(self, "_token_type") else "inconnu",
            )
            logger.error("  → Réponse complète : %s", data)
            return False

        except requests.RequestException as exc:
            logger.error("Erreur réseau lors de la publication Facebook : %s", exc)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("Erreur inattendue lors de la publication Facebook : %s", exc)
            return False

    def post_to_instagram(self, message: str, image_url: str = "") -> bool:
        """
        Publie un post sur Instagram via l'API Graph.

        :param message: Contenu du post
        :param image_url: URL publique HTTPS de l'image (requis pour Instagram)
        :return: True si publié (ou simulé), False en cas d'échec
        """
        if not message:
            logger.error("Message vide — impossible de publier sur Instagram")
            return False

        if not image_url:
            logger.error(
                "Instagram requiert une image URL — impossible de publier sans image. "
                "Fournissez image_url ou désactivez Instagram."
            )
            return False

        if not config.INSTAGRAM_ACCOUNT_ID:
            logger.error(
                "INSTAGRAM_ACCOUNT_ID manquant — impossible de publier sur Instagram. "
                "Renseignez INSTAGRAM_ACCOUNT_ID dans .env"
            )
            return False

        if config.DRY_RUN:
            print("\n" + "=" * 60)
            print("MODE TEST (DRY RUN) — POST INSTAGRAM NON ENVOYÉ")
            print("=" * 60)
            print(f"Instagram Account ID : {config.INSTAGRAM_ACCOUNT_ID}")
            print(f"Message : {message}")
            print(f"Image URL : {image_url}")
            print("=" * 60 + "\n")
            logger.info("Dry-run : post Instagram affiché dans la console")
            return True

        if not self._is_configured:
            logger.error("Client Facebook non configuré — appelez configure() d'abord")
            return False

        try:
            valid_image_url = get_valid_instagram_image(message, image_url)
            create_url = f"{GRAPH_API_URL}/{config.INSTAGRAM_ACCOUNT_ID}/media"
            create_params = {
                "access_token": config.FB_PAGE_ACCESS_TOKEN,
                "caption": message,
                "image_url": valid_image_url,
            }
            logger.debug("Création du container Instagram : POST %s", create_url)
            create_response = requests.post(create_url, data=create_params, timeout=30)
            create_data = create_response.json()

            if create_response.status_code != 200 or "id" not in create_data:
                self._record_error(create_data)
                logger.error(
                    "Erreur création container Instagram (%d) : code=%s message=%s | ig_user_id=%s",
                    create_response.status_code,
                    create_data.get("error", {}).get("code"),
                    create_data.get("error", {}).get("message"),
                    config.INSTAGRAM_ACCOUNT_ID,
                )
                logger.error("  → Réponse complète : %s", create_data)
                return False

            container_id = create_data["id"]
            logger.info("Container Instagram créé — ID : %s", container_id)

            publish_url = f"{GRAPH_API_URL}/{config.INSTAGRAM_ACCOUNT_ID}/media_publish"
            publish_params = {
                "access_token": config.FB_PAGE_ACCESS_TOKEN,
                "creation_id": container_id,
            }

            publish_response = None
            publish_data = {}
            for attempt in range(1, 4):
                logger.debug("Publication du post Instagram (tentative %d/3) : POST %s", attempt, publish_url)
                publish_response = requests.post(publish_url, data=publish_params, timeout=30)
                publish_data = publish_response.json()

                if publish_response.status_code == 200 and publish_data.get("id"):
                    post_id = publish_data["id"]
                    logger.info("Post Instagram publié avec succès — ID : %s", post_id)
                    return True

                if publish_response.status_code == 400 and publish_data.get("error", {}).get("code") == 9007:
                    logger.warning("Instagram : conteneur pas encore prêt, nouvelle tentative dans 3s...")
                    time.sleep(3)
                    continue

                break

            self._record_error(publish_data)
            logger.error(
                "Erreur publication Instagram (%d) : code=%s message=%s | ig_user_id=%s",
                publish_response.status_code if publish_response is not None else -1,
                publish_data.get("error", {}).get("code"),
                publish_data.get("error", {}).get("message"),
                config.INSTAGRAM_ACCOUNT_ID,
            )
            logger.error("  → Réponse complète : %s", publish_data)
            return False

        except requests.RequestException as exc:
            logger.error("Erreur réseau lors de la publication Instagram : %s", exc)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("Erreur inattendue lors de la publication Instagram : %s", exc)
            return False

    def post_to_threads(self, message: str, image_url: str = "") -> bool:
        """
        Publie un post texte (ou image) sur Threads via l'API Threads.

        Utilise l'API Threads (https://graph.threads.net/v1.0) en 2 étapes :
          1. Crée un container (POST /{THREADS_USER_ID}/threads)
          2. Publie le container (POST /{THREADS_USER_ID}/threads_publish)

        :param message: Contenu du post Threads
        :param image_url: URL publique HTTPS de l'image (optionnel)
        :return: True si publié (ou simulé), False en cas d'échec
        """
        if not message:
            logger.error("Message vide — impossible de publier sur Threads")
            return False

        if not config.THREADS_USER_ID:
            logger.error(
                "THREADS_USER_ID manquant — impossible de publier sur Threads. "
                "Renseignez THREADS_USER_ID dans .env"
            )
            return False

        if not config.THREADS_ACCESS_TOKEN:
            logger.error(
                "THREADS_ACCESS_TOKEN manquant — impossible de publier sur Threads. "
                "Renseignez THREADS_ACCESS_TOKEN dans .env"
            )
            return False

        if config.DRY_RUN:
            print("\n" + "=" * 60)
            print("MODE TEST (DRY RUN) — POST THREADS NON ENVOYÉ")
            print("=" * 60)
            print(f"Threads User ID : {config.THREADS_USER_ID}")
            print(f"Message : {message}")
            if image_url:
                print(f"Image URL : {image_url}")
            print("=" * 60 + "\n")
            logger.info("Dry-run : post Threads affiché dans la console")
            return True

        if not self._is_configured:
            logger.error("Client Facebook non configuré — appelez configure() d'abord")
            return False

        try:
            refreshed_token = refresh_threads_token(config.THREADS_ACCESS_TOKEN)
            if refreshed_token != config.THREADS_ACCESS_TOKEN:
                config.THREADS_ACCESS_TOKEN = refreshed_token
                logger.info("Token Threads rafraîchi automatiquement avant publication.")

            create_url = f"{THREADS_API_URL}/{config.THREADS_USER_ID}/threads"
            create_params = {
                "access_token": config.THREADS_ACCESS_TOKEN,
                "text": message,
            }

            if image_url:
                create_params["media_type"] = "IMAGE"
                create_params["image_url"] = image_url
            else:
                create_params["media_type"] = "TEXT"

            logger.debug("Création du container Threads : POST %s", create_url)
            create_response = requests.post(create_url, data=create_params, timeout=30)
            create_data = create_response.json()

            if create_response.status_code != 200 or "id" not in create_data:
                self._record_error(create_data)
                logger.error(
                    "Erreur création container Threads (%d) : code=%s message=%s | user_id=%s",
                    create_response.status_code,
                    create_data.get("error", {}).get("code"),
                    create_data.get("error", {}).get("message"),
                    config.THREADS_USER_ID,
                )
                logger.error("  → Réponse complète : %s", create_data)
                return False

            container_id = create_data["id"]
            logger.info("Container Threads créé — ID : %s", container_id)

            publish_url = f"{THREADS_API_URL}/{config.THREADS_USER_ID}/threads_publish"
            publish_params = {
                "access_token": config.THREADS_ACCESS_TOKEN,
                "creation_id": container_id,
            }

            publish_response = None
            publish_data = {}
            for attempt in range(1, 4):
                logger.debug("Publication du container Threads (tentative %d/3) : POST %s", attempt, publish_url)
                publish_response = requests.post(publish_url, data=publish_params, timeout=30)
                publish_data = publish_response.json() if publish_response is not None else {}

                if publish_response is not None and publish_response.status_code == 200 and publish_data.get("id"):
                    post_id = publish_data["id"]
                    logger.info("Post Threads publié avec succès — ID : %s", post_id)
                    return True

                if publish_response is not None and publish_response.status_code == 400 and publish_data.get("error", {}).get("code") == 24:
                    logger.warning("Threads : conteneur pas encore prêt, nouvelle tentative dans 3s...")
                    time.sleep(3)
                    continue

                break

            self._record_error(publish_data)
            logger.error(
                "Erreur publication Threads (%d) : code=%s message=%s | user_id=%s",
                publish_response.status_code if publish_response is not None else -1,
                publish_data.get("error", {}).get("code"),
                publish_data.get("error", {}).get("message"),
                config.THREADS_USER_ID,
            )
            logger.error("  → Réponse complète : %s", publish_data)
            return False

        except requests.RequestException as exc:
            logger.error("Erreur réseau lors de la publication Threads : %s", exc)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("Erreur inattendue lors de la publication Threads : %s", exc)
            return False
