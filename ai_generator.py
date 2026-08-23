"""Générateur IA de posts - Version optimisée
Transforme un article en post optimisé en français avec UN SEUL appel LLM.
"""

import json
import logging
import re
import time
from typing import Optional
from openai import OpenAI

import config

logger = logging.getLogger(__name__)

HARD_LIMIT = config.MAX_POST_LENGTH

def _truncate_post(text: str, url: str, max_length: int = HARD_LIMIT) -> str:
    if len(text) <= max_length:
        return text
    logger.warning(f"Post trop long ({len(text)} caractères) - troncature")
    url_len = len(url) + 1
    suffix_needed = url_len + 50
    head_len = max(60, max_length - suffix_needed)
    head = text[:head_len].rstrip()
    tail = text[-suffix_needed:].lstrip()
    truncated = f"{head}… {tail}"
    return truncated[:max_length-1] + "…" if len(truncated) > max_length else truncated

def _clean_generated_post(raw: str) -> str:
    text = raw.strip()
    if len(text) >= 2 and text[0] in ('"', "'", "«") and text[-1] in ('"', "'", "»"):
        text = text[1:-1].strip()
    return re.sub(r"\s+", " ", text)

def _extract_text_from_json(raw: str) -> Optional[str]:
    if not (text := raw.strip()).startswith("{"):
        return None
    try:
        data = json.loads(text)
        return next((str(v).strip() for v in data.values() if isinstance(v, str)), None)
    except (json.JSONDecodeError, TypeError):
        return None

def _call_llm(messages: list, max_tokens: int = 300) -> Optional[str]:
    if not (config.LLM_API_KEY or config.GROQ_API_KEY):
        logger.warning("Aucun fournisseur LLM configuré")
        return None

    providers = []
    if config.LLM_API_KEY:
        providers.append({
            "name": "Gemini", 
            "key": config.LLM_API_KEY,
            "base_url": config.LLM_BASE_URL,
            "model": config.LLM_MODEL
        })
    if config.GROQ_API_KEY:
        providers.append({
            "name": "Groq",
            "key": config.GROQ_API_KEY,
            "base_url": config.GROQ_BASE_URL,
            "model": config.GROQ_MODEL
        })

    for provider in providers:
        try:
            logger.info(f"Tentative LLM {provider['name']}")
            client = OpenAI(
                api_key=provider["key"],
                base_url=provider["base_url"],
                timeout=60.0,
            )
            response = client.chat.completions.create(
                model=provider["model"],
                messages=messages,
                temperature=0.7,
                max_tokens=max_tokens
            )
            logger.info("Succès avec %s", provider["name"])
            return response.choices[0].message.content
        except Exception as exc:
            # Log détaillé : type d'exception + base_url pour diagnostic
            # (ex : secret mal copié, URL invalide, réseau, quota…)
            logger.warning(
                "Échec %s (base_url=%s, model=%s) — %s : %s",
                provider["name"],
                provider["base_url"],
                provider["model"],
                type(exc).__name__,
                exc,
            )
    logger.warning("Tous les fournisseurs LLM ont échoué")
    return None

def generate_french_title(title: str, source: str, summary: str = "") -> str:
    max_attempts = 3
    prompt = config.AI_TITLE_PROMPT_TEMPLATE.format(
        title=title,
        source=source,
        summary=summary or "Pas de résumé disponible"
    )
    for attempt in range(max_attempts):
        raw_title = _call_llm([
            {"role": "system", "content": config.AI_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ], max_tokens=120)
        if raw_title:
            french_title = _clean_generated_post(raw_title)
            return french_title
        time.sleep(config.AI_GENERATION_DELAY)
    return title

def _parse_llm_json(raw_response: str) -> Optional[dict]:
    """
    Extrait et valide l'objet JSON {title, body, long_body} d'une réponse LLM.

    Tolère les balises markdown (```json ... ```), le texte avant/après
    l'objet JSON, et les espaces superflus.

    :return: dict avec les clés title/body/long_body, ou None si non conforme
    """
    clean = raw_response.strip()
    # Suppression des balises markdown éventuelles
    clean = re.sub(r"^```(?:json)?\s*", "", clean)
    clean = re.sub(r"\s*```$", "", clean).strip()

    # Extraction de la portion { ... } la plus large
    start, end = clean.find("{"), clean.rfind("}")
    if start == -1 or end <= start:
        return None

    try:
        data = json.loads(clean[start:end + 1])
    except json.JSONDecodeError:
        return None

    if isinstance(data, dict) and {"title", "body", "long_body"}.issubset(data.keys()):
        return {
            "title": str(data["title"]).strip(),
            "body": str(data["body"]).strip(),
            "long_body": str(data["long_body"]).strip(),
        }
    return None


def generate_complete_post(title: str, url: str, source: str, summary: str = "") -> Optional[dict]:
    prompt = config.AI_LONG_POST_PROMPT_TEMPLATE.format(
        title=title,
        source=source,
        url=url,
        summary=summary or "Pas de résumé disponible",
        max_length=HARD_LIMIT
    )
    
    raw_response = _call_llm([
        {"role": "system", "content": config.AI_SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ], max_tokens=800)
    
    if not raw_response:
        logger.warning("Mode dégradé activé")
        return {
            "title": title,
            "body": f"{title}\n{url} #FaitsDivers",
            "long_body": f"{title}\n\n{summary or ''}\n\n{url} #FaitsDivers",
            "fallback_mode": True
        }

    result = _parse_llm_json(raw_response)
    if result:
        logger.info("Post complet généré en un seul appel LLM")
        return result

    # La réponse n'est pas du JSON conforme : on réutilise quand même le texte
    # généré plutôt que de le jeter (mode dégradé local).
    logger.warning("Réponse LLM non conforme au format JSON attendu — utilisation du texte brut")
    text = _clean_generated_post(raw_response)
    if text:
        return {
            "title": title,
            "body": _truncate_post(f"{text}", url),
            "long_body": _truncate_post(f"{text}", url),
            "fallback_mode": True,
        }

    return {
        "title": title,
        "body": f"{title}\n{url} #FaitsDivers",
        "long_body": f"{title}\n\n{summary or ''}\n\n{url} #FaitsDivers",
        "fallback_mode": True
    }
