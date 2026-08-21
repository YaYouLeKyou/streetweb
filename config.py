"""
Configuration centrale de Streetweb — Veille Faits Divers & Culture Urbaine.

Centralise :
  - les clés API (chargées depuis .env)
  - la liste des flux RSS Faits Divers & Culture Urbaine
  - la planification (4 fois par jour)
  - le prompt de génération IA
"""

import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Chargement des variables d'environnement (.env)
load_dotenv()

# ─────────────────────────────────────────────────────────────
# API LLM (OpenAI SDK compatible — Gemini / Groq)
# ─────────────────────────────────────────────────────────────
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")
# Nombre max de tokens — Gemini a un mode "thinking" qui consomme
# des tokens avant la réponse. 2000 garantit un post complet.
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))

# ─────────────────────────────────────────────────────────────
# Fallback LLM — Groq (si Gemini est indisponible)
# ─────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "groq/compound-mini")

# ─────────────────────────────────────────────────────────────
# API Facebook / Meta (Graph API) — Facebook + Instagram
# ─────────────────────────────────────────────────────────────
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", os.getenv("META_ACCESS_TOKEN", ""))
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "")

# ── Renouvellement automatique des tokens ────────────────────
# Identifiants de l'application Facebook (nécessaires pour fb_exchange_token)
# https://developers.facebook.com/apps/ → votre app → Paramètres → Identifiants
FB_APP_ID = os.getenv("FB_APP_ID", "")
FB_APP_SECRET = os.getenv("FB_APP_SECRET", "")

# Nombre de jours entre deux renouvellements automatiques des tokens.
# Les tokens Meta durent 60 jours — un renouvellement tous les
# 30 jours garantit une marge de sécurité confortable.
TOKEN_RENEWAL_DAYS = int(os.getenv("TOKEN_RENEWAL_DAYS", "30"))

# ─────────────────────────────────────────────────────────────
# Flux RSS spécialisés « Faits Divers & Culture Urbaine »
# ─────────────────────────────────────────────────────────────
DEFAULT_RSS_FEEDS = [
    # 🇫🇷 Francophone — Faits divers & Société
    "https://www.leparisien.fr/faits-divers/rss.xml",
    # 20minutes, bfmtv, francetvinfo, lemonde sont desagreges/redirecteurs
    # et renvoient 403/400/404 depuis les hebergeurs : desactives pour
    # ne pas bloquer le worker pendant 20s x 3 retries chacun.
    # 🇫🇷 Culture urbaine — Rap, Street Art, Tendances
    "https://www.booska-p.com/feed/",
    "https://www.rap2france.com/feed/",
]

# Timeout/retry RSS (raccourcis pour ne pas bloquer le worker)
FEED_TIMEOUT = 8  # secondes
FEED_MAX_RETRIES = 2
FEED_RETRY_BACKOFF = 2  # 1s, 2s

# Liste des flux effectifs :
#   - Si la variable d'environnement RSS_FEED_URLS est définie, on l'utilise
#   - Sinon, on retombe sur la liste par défaut ci-dessus
_env_feeds = os.getenv("RSS_FEED_URLS", "").strip()
if _env_feeds:
    RSS_FEEDS = [url.strip() for url in _env_feeds.split(",") if url.strip()]
else:
    RSS_FEEDS = DEFAULT_RSS_FEEDS

# ─────────────────────────────────────────────────────────────
# Base de données SQLite (anti-doublons)
# ─────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "streetweb_bot.db")

# ─────────────────────────────────────────────────────────────
# Planification — Posts par heures fixes
# Défaut : 07:00, 12:00, 17:00, 20:00 heure de PARIS (configurable via .env)
# Les heures saisies dans l'interface / .env sont TOUJOURS en heure de Paris.
# La conversion vers UTC est automatique (gère l'heure d'été/hiver).
# ─────────────────────────────────────────────────────────────
DEFAULT_SCHEDULE_TIMES = ["07:00", "12:00", "17:00", "20:00"]

# Fuseau horaire de publication (heure de Paris)
LOCAL_TIMEZONE = "Europe/Paris"

_env_schedule = os.getenv("SCHEDULE_TIMES", "").strip()
if _env_schedule:
    SCHEDULE_TIMES = [
        t.strip() for t in _env_schedule.split(",") if t.strip()
    ]
else:
    SCHEDULE_TIMES = DEFAULT_SCHEDULE_TIMES

# Fréquence de génération des posts (en heures)
# Défaut : 0 = désactivé (utiliser les heures fixes)
NEWS_INTERVAL_HOURS = int(os.getenv("NEWS_INTERVAL_HOURS", "0"))


def get_paris_tz():
    """
    Retourne le fuseau horaire de Paris.
    Utilise zoneinfo (stdlib) avec fallback pytz si indisponible.

    :return: Objet tzinfo (zoneinfo.ZoneInfo ou pytz.timezone)
    """
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(LOCAL_TIMEZONE)
    except (ImportError, KeyError):
        try:
            import pytz
            return pytz.timezone(LOCAL_TIMEZONE)
        except (ImportError, KeyError) as exc:
            logger.warning(
                "Impossible de charger le fuseau %s (%s) — fallback UTC",
                LOCAL_TIMEZONE,
                exc,
            )
            from datetime import timezone
            return timezone.utc


def paris_time_to_utc(hhmm: str) -> str:
    """
    Convertit une heure de Paris (HH:MM) en heure UTC (HH:MM).
    Gère automatiquement l'heure d'été (UTC+2) et l'heure d'hiver (UTC+1).
    Utilise la date ACTUELLE pour un décalage correct été/hiver.

    :param hhmm: Heure au format HH:MM (heure de Paris)
    :return: Heure UTC correspondante au format HH:MM
    """
    try:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo

        hour_str, minute_str = hhmm.strip().split(":")
        paris_tz = ZoneInfo(LOCAL_TIMEZONE)
        # Utilise la date du jour pour un calcul correct été/hiver.
        now = datetime.now(paris_tz)
        naive = now.replace(hour=int(hour_str), minute=int(minute_str), second=0, microsecond=0)
        paris_aware = naive.replace(tzinfo=paris_tz)
        utc_dt = paris_aware.astimezone(timezone.utc)
        return utc_dt.strftime("%H:%M")
    except (ValueError, TypeError, ImportError, KeyError) as exc:
        # Fallback : if zoneinfo est indisponible (ex: Windows sans tzdata),
        # on utilise pytz pour une conversion fiable.
        try:
            from datetime import datetime, timezone
            import pytz

            hour_str, minute_str = hhmm.strip().split(":")
            paris_tz = pytz.timezone(LOCAL_TIMEZONE)
            now_paris = datetime.now(paris_tz)
            naive_local = now_paris.replace(
                hour=int(hour_str),
                minute=int(minute_str),
                second=0,
                microsecond=0,
                tzinfo=None,
            )
            local_aware = paris_tz.localize(naive_local, is_dst=None)
            utc_dt = local_aware.astimezone(timezone.utc)
            return utc_dt.strftime("%H:%M")
        except (ValueError, TypeError, ImportError) as fallback_exc:
            logger.warning(
                "Impossible de convertir %s Paris → UTC (%s). Heure utilisée telle quelle.",
                hhmm, fallback_exc,
            )
            return hhmm


def utc_time_to_paris(hhmm: str) -> str:
    """
    Convertit une heure UTC (HH:MM) en heure de Paris (HH:MM).
    Gère automatiquement l'heure d'été (UTC+2) et l'heure d'hiver (UTC+1).
    Utilise la date ACTUELLE pour un décalage correct été/hiver.

    :param hhmm: Heure au format HH:MM (UTC)
    :return: Heure de Paris correspondante au format HH:MM
    """
    try:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo

        hour_str, minute_str = hhmm.strip().split(":")
        paris_tz = ZoneInfo(LOCAL_TIMEZONE)
        # Utilise la date du jour pour un calcul correct été/hiver.
        now_utc = datetime.now(timezone.utc)
        naive_utc = now_utc.replace(hour=int(hour_str), minute=int(minute_str), second=0, microsecond=0)
        paris_dt = naive_utc.astimezone(paris_tz)
        return paris_dt.strftime("%H:%M")
    except (ValueError, TypeError, ImportError) as exc:
        logger.warning(
            "Impossible de convertir %s UTC → Paris (%s). Heure utilisée telle quelle.",
            hhmm, exc,
        )
        return hhmm

# ─────────────────────────────────────────────────────────────
# Serveur web (Flask)
# ─────────────────────────────────────────────────────────────
WEB_PORT = int(os.getenv("WEB_PORT", "5000"))

# ─────────────────────────────────────────────────────────────
# Publication
# ─────────────────────────────────────────────────────────────
MAX_POST_LENGTH = 2200  # Limite de sécurité pour les posts Facebook/Instagram
MAX_ARTICLES_TO_PROCESS = 30  # articles maximum scannés par exécution

# ─────────────────────────────────────────────────────────────
# Génération IA — espacement des appels API
# ─────────────────────────────────────────────────────────────
# Délai (en secondes) entre deux appels à l'API LLM lors de la
# génération de plusieurs propositions (anti rate-limit TPM).
# Il est configurable via la variable d'environnement AI_GENERATION_DELAY.
AI_GENERATION_DELAY = int(os.getenv("AI_GENERATION_DELAY", "15"))

# ─────────────────────────────────────────────────────────────
# Historique des posts
# ─────────────────────────────────────────────────────────────
# Nombre maximum d'articles conservés dans l'historique.
# Au-delà, les plus anciens sont automatiquement supprimés.
MAX_HISTORY_SIZE = int(os.getenv("MAX_HISTORY_SIZE", "50"))

# ─────────────────────────────────────────────────────────────
# Mode test
# ─────────────────────────────────────────────────────────────
TEST_ON_STARTUP = os.getenv("TEST_ON_STARTUP", "false").strip().lower() == "true"

# ─────────────────────────────────────────────────────────────
# Mode simulation (Dry-Run)
# ─────────────────────────────────────────────────────────────
# true  = affiche le post dans la console, ne publie PAS sur Facebook/Instagram
# false = publie réellement sur Facebook/Instagram (comportement normal)
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() in ("true", "1", "yes")

# ─────────────────────────────────────────────────────────────
# Notification email — alerte en cas de token expiré
# ─────────────────────────────────────────────────────────────
# Adresse email qui reçoit les alertes de token expiré
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "yanes75@hotmail.fr")

# Activation de l'envoi d'emails (true/false)
SMTP_ENABLED = os.getenv("SMTP_ENABLED", "false").strip().lower() in ("true", "1", "yes")

# Configuration SMTP
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_TLS = os.getenv("SMTP_TLS", "true").strip().lower() in ("true", "1", "yes")
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME)

# ─────────────────────────────────────────────────────────────
# Prompt système pour la génération du post
# ─────────────────────────────────────────────────────────────
AI_SYSTEM_PROMPT = (
    "Tu es un journaliste expert en faits divers sensationnalistes et en culture urbaine. "
    "Ton style est percutant, immersif et accrocheur, adapté aux réseaux sociaux. "
    "Tu rédiges exclusivement en français, sans aucun mot anglais. "
    "Tu es spécialisé dans le rap, le street art, les tendances urbaines et les faits de société."
)

AI_USER_PROMPT_TEMPLATE = (
    "Voici le contenu d'un article de presse :\n"
    "\n"
    "Titre : {title}\n"
    "Source : {source}\n"
    "URL : {url}\n"
    "Résumé : {summary}\n"
    "\n"
    "Rédige un post en français respectant STRICTEMENT ces règles :\n"
    "1. Maximum {max_length} caractères (compte incluant les hashtags et le lien).\n"
    "2. Un ton journalistique percutant, avec une accroche qui capte l'attention immédiatement.\n"
    "3. Une synthèse claire des points essentiels de l'article.\n"
    "4. Termine par 3 hashtags ciblés et pertinents, par exemple #FaitsDivers #CultureUrbaine #Street.\n"
    "5. N'utilise que du français : pas d'anglais, pas d'emojis, pas de citation du titre exact.\n"
    "6. Le post doit se terminer par le lien de l'article : {url}\n"
    "\n"
    "Renvoie UNIQUEMENT le texte du post, sans guillemets ni commentaire."
)

AI_TITLE_PROMPT_TEMPLATE = (
    "Voici le titre d'un article de presse : {title}\n"
    "Source : {source}\n"
    "Résumé : {summary}\n"
    "\n"
    "Rédige un nouveau titre en français, percutant et accrocheur, adapté à un public "
    "passionné de faits divers et de culture urbaine. "
    "Le titre doit être court (maximum 120 caractères), sans emojis, sans guillemets, "
    "et sans aucun mot anglais. Renvoie UNIQUEMENT le titre."
)

AI_LONG_POST_PROMPT_TEMPLATE = (
    "Voici le contenu d'un article de presse :\n"
    "\n"
    "Titre : {title}\n"
    "Source : {source}\n"
    "URL : {url}\n"
    "Résumé : {summary}\n"
    "\n"
    "Rédige un post LONG en français respectant STRICTEMENT ces règles :\n"
    "1. Maximum {max_length} caractères (compte incluant les hashtags et le lien).\n"
    "2. Un ton journalistique percutant, avec une accroche qui capte l'attention immédiatement.\n"
    "3. Développe les points essentiels de l'article : contexte, faits, réactions, conséquences.\n"
    "4. Termine par 3 hashtags ciblés et pertinents, par exemple #FaitsDivers #CultureUrbaine #Street.\n"
    "5. N'utilise que du français : pas d'anglais, pas d'emojis, pas de citation du titre exact.\n"
    "6. Le post doit se terminer par le lien de l'article : {url}\n"
    "\n"
    "Renvoie UNIQUEMENT le texte du post, sans guillemets ni commentaire."
)
