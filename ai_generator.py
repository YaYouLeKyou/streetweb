"""
Générateur IA de posts — DeepSeek / OpenAI (SDK OpenAI compatible).

Transforme un article RSS en post optimisé en français,
avec 3 hashtags ciblés et un ton journalistique percutant
pour les faits divers & la culture urbaine.
"""

import logging
import re
import time
from typing import Optional

from openai import OpenAI

import config

logger = logging.getLogger(__name__)

# Limite stricte imposée à l'IA (marge de sécurité pour Facebook/Instagram)
HARD_LIMIT = config.MAX_POST_LENGTH


def _truncate_post(text: str, url: str, max_length: int = HARD_LIMIT) -> str:
    """
    Tronque proprement un post trop long en conservant la fin (lien + hashtags).

    Stratégie : si le texte dépasse la limite, on coupe le milieu
    en conservant le début (accroche) et la fin (lien + hashtags).
    """
    if len(text) <= max_length:
        return text

    logger.warning("Post généré trop long (%d caractères) — troncature", len(text))

    # Taille des éléments de fin à préserver
    url_len = len(url) + 1
    suffix_needed = url_len + 50  # hashtags + espace de respiration

    head_len = max(60, max_length - suffix_needed)
    head = text[:head_len].rstrip()
    tail = text[-suffix_needed:].lstrip()

    # Ajout d'une ellipse de séparation
    truncated = f"{head}… {tail}"

    if len(truncated) > max_length:
        truncated = truncated[: max_length - 1].rstrip() + "…"

    return truncated


def _clean_generated_post(raw: str) -> str:
    """Nettoie la réponse de l'IA (guillemets parasites, retours à la ligne)."""
    text = raw.strip()
    # Retire les guillemets ouvrants/fermants si l'IA a encadré le post
    if len(text) >= 2 and text[0] in ('"', "'", "«") and text[-1] in ('"', "'", "»"):
        text = text[1:-1].strip()
    # Remplace les retours à la ligne par des espaces
    text = re.sub(r"\s+", " ", text)
    return text


def _call_llm(messages: list, max_tokens: int = 300) -> Optional[str]:
    """
    Appel générique à l'API LLM avec délai anti-rate-limit.
    Essaie d'abord Gemini, puis Groq. Si les deux sont indisponibles,
    retourne None et le mode dégradé sera utilisé.
    """
    if not config.LLM_API_KEY and not config.GROQ_API_KEY:
        logger.warning("Aucun fournisseur LLM configuré — mode dégradé sera utilisé")
        return None

    providers = []

    if config.LLM_API_KEY:
        providers.append({
            "name": "Gemini",
            "key": config.LLM_API_KEY,
            "base_url": config.LLM_BASE_URL,
            "model": config.LLM_MODEL,
        })

    if config.GROQ_API_KEY:
        providers.append({
            "name": "Groq",
            "key": config.GROQ_API_KEY,
            "base_url": config.GROQ_BASE_URL,
            "model": config.GROQ_MODEL,
        })

    for provider in providers:
        try:
            logger.info("Tentative LLM : %s (%s)...", provider["name"], provider["model"])
            client = OpenAI(api_key=provider["key"], base_url=provider["base_url"])
            response = client.chat.completions.create(
                model=provider["model"],
                messages=messages,
                temperature=0.7,
                max_tokens=max_tokens,
            )
            logger.info("Succès avec %s", provider["name"])
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("Échec %s : %s", provider["name"], exc)

    logger.warning("Tous les fournisseurs LLM ont échoué — mode dégradé sera utilisé")
    return None


def _fallback_post(title: str, url: str, max_length: int = HARD_LIMIT) -> str:
    """
    Mode dégradé : construit un post simple sans IA.
    Utilisé quand tous les providers LLM sont indisponibles.
    """
    post = f"{title}\n{url}"
    if len(post) > max_length:
        post = post[: max_length - 3].rstrip() + "..."
    hashtag = " #FaitsDivers"
    if len(post) + len(hashtag) <= max_length:
        post = f"{post}{hashtag}"
    return post.strip()


def generate_post(title: str, url: str, source: str, summary: str = "") -> Optional[str]:
    """
    Génère un post court en français à partir d'un article.

    :param title: Titre de l'article
    :param url: Lien de l'article
    :param source: Nom de la source
    :param summary: Résumé de l'article
    :return: Post prêt à publier (ou None si erreur)
    """
    prompt = config.AI_USER_PROMPT_TEMPLATE.format(
        title=title,
        source=source,
        url=url,
        summary=summary or "Pas de résumé disponible.",
        max_length=HARD_LIMIT,
    )

    raw_post = _call_llm(
        messages=[
            {"role": "system", "content": config.AI_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=300,
    )
    if not raw_post:
        logger.warning("Mode dégradé activé pour generate_post : publication du lien seulement")
        return _fallback_post(title, url)

    time.sleep(config.AI_GENERATION_DELAY)

    post = _clean_generated_post(raw_post)

    # Force la présence du lien à la fin si l'IA ne l'a pas inclus
    if url not in post:
        if len(post) + len(url) + 2 > HARD_LIMIT:
            post = _truncate_post(post, url)
        post = f"{post}\n{url}".strip()

    # Vérifie les hashtags — ajoute un fallback #FaitsDivers si absent
    if not re.search(r"#[\wéàèéâîôûç]+", post):
        hashtag = " #FaitsDivers"
        if len(post) + len(hashtag) <= HARD_LIMIT:
            post = f"{post}{hashtag}"
        else:
            post = _truncate_post(post + hashtag, url)

    # Troncature finale de sécurité
    if len(post) > HARD_LIMIT:
        post = _truncate_post(post, url)

    logger.info("Post généré : %d caractères", len(post))
    return post


def generate_long_post(title: str, url: str, source: str, summary: str = "") -> Optional[str]:
    """
    Génère un post long en français à partir d'un article.

    :param title: Titre de l'article
    :param url: Lien de l'article
    :param source: Nom de la source
    :param summary: Résumé de l'article
    :return: Post long prêt à publier (ou None si erreur)
    """
    prompt = config.AI_LONG_POST_PROMPT_TEMPLATE.format(
        title=title,
        source=source,
        url=url,
        summary=summary or "Pas de résumé disponible.",
        max_length=HARD_LIMIT,
    )

    raw_post = _call_llm(
        messages=[
            {"role": "system", "content": config.AI_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=800,
    )
    if not raw_post:
        logger.warning("Mode dégradé activé pour generate_long_post : publication du lien seulement")
        return _fallback_post(title, url)

    time.sleep(config.AI_GENERATION_DELAY)

    post = _clean_generated_post(raw_post)

    # Force la présence du lien à la fin si l'IA ne l'a pas inclus
    if url not in post:
        if len(post) + len(url) + 2 > HARD_LIMIT:
            post = _truncate_post(post, url)
        post = f"{post}\n{url}".strip()

    # Vérifie les hashtags — ajoute un fallback #FaitsDivers si absent
    if not re.search(r"#[\wéàèéâîôûç]+", post):
        hashtag = " #FaitsDivers"
        if len(post) + len(hashtag) <= HARD_LIMIT:
            post = f"{post}{hashtag}"
        else:
            post = _truncate_post(post + hashtag, url)

    # Troncature finale de sécurité
    if len(post) > HARD_LIMIT:
        post = _truncate_post(post, url)

    logger.info("Post long généré : %d caractères", len(post))
    return post


def generate_french_title(title: str, source: str, summary: str = "", max_attempts: int = 1) -> Optional[str]:
    """
    Génère un titre français à partir d'un article, avec retry automatique.

    :param title: Titre original
    :param source: Nom de la source
    :param summary: Résumé de l'article
    :param max_attempts: Nombre maximum de tentatives
    :return: Titre français ou titre original si échec
    """
    prompt = config.AI_TITLE_PROMPT_TEMPLATE.format(
        title=title,
        source=source,
        summary=summary or "Pas de résumé disponible.",
    )

    for attempt in range(max_attempts):
        raw_title = _call_llm(
            messages=[
                {"role": "system", "content": config.AI_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=120,
        )
        if not raw_title:
            continue

        time.sleep(config.AI_GENERATION_DELAY)

        french_title = _clean_generated_post(raw_title)
        if french_title:
            logger.info("Titre français généré : %s", french_title)
            return french_title

    logger.warning("Échec de la génération du titre français après %d tentatives — titre original conservé", max_attempts)
    return title

def generate_complete_post(title: str, url: str, source: str, summary: str = "") -> Optional[dict]:
    """
    Génère un post complet avec titre et corps en UN SEUL appel LLM.
    Optimisation pour éviter les appels multiples à Gemini.

    :param title: Titre de l'article
    :param url: Lien de l'article
    :param source: Nom de la source
    :param summary: Résumé de l'article
    :return: dict avec 'title' et 'body', ou None si échec
    """
    prompt = f"""Génère un post complet en français avec les éléments suivants :

    1. Un titre français accrocheur et optimisé pour les réseaux sociaux
    2. Un texte de post court et percutant avec 3 hashtags pertinents
    3. Un texte de post long et détaillé pour Facebook

    Format de réponse requis (JSON valide) :
    {{
        "title": "Titre français accrocheur",
        "body": "Texte court avec hashtags et lien",
        "long_body": "Texte long détaillé avec lien"
    }}

    Article original :
    Titre: {title}
    Source: {source}
    URL: {url}
    Résumé: {summary or "Pas de résumé disponible."}"""

    raw_response = _call_llm(
        messages=[
            {"role": "system", "content": config.AI_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=800,
    )

    if not raw_response:
        logger.warning("Mode dégradé activé pour generate_complete_post")
        return {
            "title": title,
            "body": f"{title}\n{url} #FaitsDivers",
            "long_body": f"{title}\n\n{summary or ''}\n\n{url} #FaitsDivers"
        }

    time.sleep(config.AI_GENERATION_DELAY)

    try:
        import json
        # Essaye de parser le JSON directement
        result = json.loads(raw_response)
        if "title" in result and "body" in result:
            logger.info("Post complet généré en un seul appel LLM")
            return result
    except (json.JSONDecodeError, KeyError):
        # Si le parsing JSON échoue, utilise le mode dégradé
        logger.warning("Réponse LLM non conforme au format JSON attendu")
        return {
            "title": title,
            "body": f"{title}\n{url} #FaitsDivers",
            "long_body": f"{title}\n\n{summary or ''}\n\n{url} #FaitsDivers"
        }
