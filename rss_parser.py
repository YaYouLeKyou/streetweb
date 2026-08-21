"""
Parseur de flux RSS — extraction des derniers articles Faits Divers & Culture Urbaine.

Utilise la bibliothèque `feedparser` pour récupérer les articles
des flux configurés dans `config.RSS_FEEDS`.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import feedparser
import requests

import config

logger = logging.getLogger(__name__)

# Timeout et retry pour les requêtes RSS (depuis config.py)
_FEED_TIMEOUT = getattr(config, "FEED_TIMEOUT", 8)
_FEED_MAX_RETRIES = getattr(config, "FEED_MAX_RETRIES", 2)
_FEED_RETRY_BACKOFF = getattr(config, "FEED_RETRY_BACKOFF", 2)  # 1s, 2s
_FEED_USER_AGENT = "Mozilla/5.0 (compatible; Streetweb/1.0; +https://streetweb.local)"


@dataclass
class Article:
    """Représente un article extrait d'un flux RSS."""

    title: str
    url: str
    source: str
    summary: str = ""
    published: Optional[datetime] = None
    image: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Un article est valide s'il a un titre et une URL."""
        return bool(self.title and self.url)


def _extract_entry_image(entry) -> Optional[str]:
    """Essaie d'extraire une URL d'image depuis une entrée feedparser."""
    candidates = []

    if hasattr(entry, "media_content") and entry.media_content:
        for media in entry.media_content:
            if isinstance(media, dict):
                candidates.append(media.get("href") or media.get("url"))

    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if isinstance(enc, dict):
                href = enc.get("href") or enc.get("url")
                if href:
                    candidates.append(href)

    image = entry.get("image") if hasattr(entry, "get") else getattr(entry, "image", None)
    if isinstance(image, dict):
        candidates.append(image.get("href") or image.get("url"))
    elif isinstance(image, str):
        candidates.append(image)

    for url in candidates:
        if isinstance(url, str) and url.startswith("http"):
            return url

    # Cherche des images dans le HTML du résumé ou du contenu
    html = ""
    if hasattr(entry, "summary"):
        html += entry.summary or ""
    if hasattr(entry, "content"):
        for content in entry.content:
            if isinstance(content, dict):
                html += content.get("value", "") or ""

    if html:
        import re
        img_matches = re.findall(r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)', html, re.IGNORECASE)
        for img_url in img_matches:
            if img_url.startswith("http"):
                return img_url

    # Fallback : télécharge la page de l'article et cherche og:image
    article_url = entry.get("link") if hasattr(entry, "get") else getattr(entry, "link", None)
    if article_url and article_url.startswith("http"):
        return _fetch_article_image(article_url)

    return None


def _fetch_article_image(article_url: str) -> Optional[str]:
    """
    Télécharge la page de l'article et extrait l'image og:image
    ou la première image disponible dans le HTML.
    """
    try:
        response = requests.get(article_url, timeout=15, headers={"User-Agent": _FEED_USER_AGENT})
        if response.status_code != 200:
            return None

        html = response.text

        # 1. Cherche d'abord og:image
        import re
        og_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if not og_match:
            og_match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.IGNORECASE)

        if og_match:
            img_url = og_match.group(1)
            if img_url.startswith("http"):
                return img_url

        # 2. Cherche la première image dans le HTML
        img_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        for img_url in img_matches:
            if img_url.startswith("http"):
                return img_url

        return None
    except requests.RequestException:
        return None
    except Exception:  # noqa: BLE001
        return None


def _parse_date(published_parsed: tuple) -> Optional[datetime]:
    """Convertit la structure de date de feedparser en datetime UTC."""
    if not published_parsed:
        return None
    try:
        import calendar

        timestamp = calendar.timegm(published_parsed)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (ValueError, OverflowError, TypeError):
        return None


def _clean_summary(raw_summary: str) -> str:
    """Nettoie le résumé HTML en texte simple (premières phrases)."""
    if not raw_summary:
        return ""
    # Retire les balises HTML simples
    import re

    text = re.sub(r"<[^>]+>", " ", raw_summary)
    text = re.sub(r"\s+", " ", text).strip()
    # Limite à ~300 caractères
    return text[:300]


def _fetch_feed_content(feed_url: str) -> Optional[str]:
    """
    Récupère le contenu XML d'un flux RSS avec timeout et retry.

    :param feed_url: URL du flux RSS
    :return: Contenu XML brut, ou None si toutes les tentatives échouent
    """
    headers = {"User-Agent": _FEED_USER_AGENT}
    for attempt in range(1, _FEED_MAX_RETRIES + 1):
        try:
            response = requests.get(
                feed_url,
                timeout=_FEED_TIMEOUT,
                headers=headers,
            )
            response.raise_for_status()
            return response.text
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            if attempt < _FEED_MAX_RETRIES:
                wait = _FEED_RETRY_BACKOFF ** (attempt - 1)
                logger.warning(
                    "Tentative %d/%d échouée pour %s : %s — nouvelle tentative dans %ds",
                    attempt,
                    _FEED_MAX_RETRIES,
                    feed_url,
                    exc,
                    wait,
                )
                time.sleep(wait)
            else:
                logger.error(
                    "Échec définitif du flux RSS après %d tentatives : %s",
                    _FEED_MAX_RETRIES,
                    feed_url,
                )
                return None


def fetch_articles(max_items: int = None) -> List[Article]:
    """
    Récupère les derniers articles de tous les flux RSS configurés.

    :param max_items: Nombre maximum d'articles à collecter au total
    :return: Liste d'articles triés par date de publication (récent → ancien)
    """
    max_items = max_items or config.MAX_ARTICLES_TO_PROCESS
    articles: List[Article] = []

    for feed_url in config.RSS_FEEDS:
        try:
            logger.info("Scan du flux RSS : %s", feed_url)

            content = _fetch_feed_content(feed_url)
            if content is None:
                logger.warning("Flux inaccessible ou vide : %s — aucun contenu récupéré", feed_url)
                continue

            feed = feedparser.parse(content)

            if feed.bozo and not feed.entries:
                logger.warning(
                    "Flux invalide ou vide : %s — erreur : %s",
                    feed_url,
                    getattr(feed, "bozo_exception", "inconnue"),
                )
                continue

            source_name = feed.feed.get("title", feed_url) if hasattr(feed, "feed") else feed_url

            for entry in feed.entries[: max_items]:
                title = entry.get("title", "").strip()
                url = entry.get("link", "").strip()
                summary = _clean_summary(entry.get("summary", ""))
                published = _parse_date(entry.get("published_parsed"))
                image = _extract_entry_image(entry)

                article = Article(
                    title=title,
                    url=url,
                    source=source_name,
                    summary=summary,
                    published=published,
                    image=image,
                )
                if article.is_valid:
                    articles.append(article)

            logger.info("Flux %s : %d articles récupérés", feed_url, len(feed.entries[: max_items]))

        except Exception as exc:  # noqa: BLE001 — un flux ne doit pas bloquer les autres
            logger.error("Erreur lors du scan du flux %s : %s", feed_url, exc)

    # Tri : plus récent d'abord, les articles sans date en dernier
    articles.sort(
        key=lambda a: a.published or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    logger.info("Total : %d articles collectés depuis %d flux", len(articles), len(config.RSS_FEEDS))
    return articles


def fetch_new_articles(max_items: int = None) -> List[Article]:
    """
    Récupère les nouveaux articles non encore traités (anti-doublons).

    :param max_items: Nombre maximum d'articles à collecter
    :return: Liste d'articles non encore présents dans la base SQLite
    """
    from database import is_article_processed

    all_articles = fetch_articles(max_items=max_items)
    new_articles = [
        article for article in all_articles if not is_article_processed(article.url)
    ]
    logger.info("%d nouveaux articles (non encore publiés)", len(new_articles))
    return new_articles
