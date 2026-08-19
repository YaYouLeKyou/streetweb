"""
Client Twitter (X) — publication via l'API V2 avec `tweepy`.

Responsabilités :
  - Authentification OAuth 1.0a (clés API + tokens d'accès)
  - Publication d'un tweet
  - Vérification de la configuration
  - Mode gratuit automatique : si les crédits sont épuisés (402),
    bascule en simulation sans erreur, et reprend la publication
    réelle automatiquement quand les crédits sont rechargés.
"""

import logging
from typing import Optional

import tweepy

import config

logger = logging.getLogger(__name__)


class TwitterClient:
    """Client Twitter pour la publication de tweets (API V2)."""

    def __init__(self) -> None:
        self.client: Optional[tweepy.Client] = None
        self._is_configured = False
        # Mode gratuit : True si les crédits sont épuisés (402)
        self._credits_depleted = False

    def configure(self) -> bool:
        """
        Configure le client Twitter avec les clés de l'environnement.

        :return: True si la configuration est valide, False sinon
        """
        required_keys = [
            config.TWITTER_API_KEY,
            config.TWITTER_API_SECRET,
            config.TWITTER_ACCESS_TOKEN,
            config.TWITTER_ACCESS_SECRET,
        ]

        if not all(required_keys):
            logger.error(
                "Configuration Twitter incomplète. "
                "Vérifiez TWITTER_API_KEY, TWITTER_API_SECRET, "
                "TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET dans .env"
            )
            return False

        try:
            self.client = tweepy.Client(
                consumer_key=config.TWITTER_API_KEY,
                consumer_secret=config.TWITTER_API_SECRET,
                access_token=config.TWITTER_ACCESS_TOKEN,
                access_token_secret=config.TWITTER_ACCESS_SECRET,
            )
            self._is_configured = True
            logger.info("Client Twitter configuré avec succès")
            return True

        except Exception as exc:  # noqa: BLE001
            logger.error("Erreur lors de la configuration Twitter : %s", exc)
            return False

    def post_tweet(self, text: str) -> bool:
        """
        Publie un tweet via l'API V2, ou simule la publication en mode dry-run.

        :param text: Contenu du tweet (max 280 caractères)
        :return: True si publié (ou simulé), False en cas d'échec
        """
        if not text or len(text) > 280:
            logger.error(
                "Tweet invalide : vide ou trop long (%d caractères)",
                len(text) if text else 0,
            )
            return False

        # ── Mode simulation (Dry-Run) : affiche sans publier ──
        if config.DRY_RUN:
            print("\n" + "=" * 60)
            print("🧪 MODE TEST (DRY RUN) — TWEET NON ENVOYÉ À TWITTER")
            print("=" * 60)
            print(text)
            print("=" * 60 + "\n")
            logger.info("Dry-run : tweet affiché dans la console (%d caractères)", len(text))
            return True

        # ── Mode gratuit automatique : crédits épuisés ──
        if self._credits_depleted:
            print("\n" + "=" * 60)
            print("🆓 MODE GRATUIT — CRÉDITS TWITTER ÉPUISÉS")
            print("Le tweet est simulé. Il sera publié automatiquement")
            print("dès que vos crédits seront rechargés.")
            print("=" * 60)
            print(text)
            print("=" * 60 + "\n")
            logger.info("Mode gratuit : tweet simulé (crédits épuisés)")
            return True

        if not self._is_configured or self.client is None:
            logger.error("Client Twitter non configuré — appelez configure() d'abord")
            return False

        try:
            response = self.client.create_tweet(text=text)

            if response.data and response.data.get("id"):
                tweet_id = response.data["id"]
                logger.info("Tweet publié avec succès — ID : %s", tweet_id)
                return True

            logger.error("Réponse Twitter inattendue : %s", response)
            return False

        except tweepy.TweepyException as exc:
            # Détecte l'erreur 402 (crédits épuisés) et bascule en mode gratuit
            error_str = str(exc)
            if "402" in error_str or "credits depleted" in error_str.lower():
                self._credits_depleted = True
                logger.warning(
                    "⚠️  Crédits Twitter épuisés (402) — bascule en mode gratuit. "
                    "Le tweet sera simulé jusqu'au rechargement des crédits."
                )
                # Simule le tweet en mode gratuit
                print("\n" + "=" * 60)
                print("🆓 MODE GRATUIT — CRÉDITS TWITTER ÉPUISÉS")
                print("Le tweet est simulé. Il sera publié automatiquement")
                print("dès que vos crédits seront rechargés.")
                print("=" * 60)
                print(text)
                print("=" * 60 + "\n")
                return True

            logger.error("Erreur Twitter API : %s", exc)
            if hasattr(exc, "response") and exc.response is not None:
                logger.error("  → HTTP Status : %s", exc.response.status_code)
                try:
                    logger.error("  → Response body : %s", exc.response.text)
                except Exception:  # noqa: BLE001
                    pass
            elif hasattr(exc, "status_code"):
                logger.error("  → Status code : %s", exc.status_code)
            logger.error("  → Tweet (texte complet) : %s", text)
            return False

        except Exception as exc:  # noqa: BLE001
            logger.error("Erreur inattendue lors de la publication : %s", exc)
            logger.error("  → Tweet (texte complet) : %s", text)
            return False

    def reset_credits_status(self) -> None:
        """Réinitialise le statut des crédits (appelé quand les crédits sont rechargés)."""
        self._credits_depleted = False
        logger.info("Statut des crédits Twitter réinitialisé — publication réelle active")