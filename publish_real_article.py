#!/usr/bin/env python3
"""
Script pour publier un vrai article d'actualité sur Facebook et Instagram.

Usage :
    python publish_real_article.py

Ce script :
  1. Récupère les derniers articles depuis les flux RSS
  2. Génère un article complet avec l'IA
  3. Publie l'article sur Facebook et Instagram
  4. Affiche les résultats détaillés
"""

import logging
import sys
import time
from datetime import datetime

import config
import database
import facebook_client
import news_service
import rss_parser
import ai_generator

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("publish-real-article")

def publish_real_article():
    """Publie un vrai article d'actualité sur Facebook et Instagram."""
    print("\n" + "=" * 60)
    print("📰 PUBLICATION D'UN VRAI ARTICLE D'ACTUALITÉ")
    print("=" * 60)

    # Initialiser la base de données
    database.init_db()

    # Récupérer les derniers articles
    print("🔍 Récupération des derniers articles depuis les flux RSS...")
    articles = rss_parser.fetch_new_articles(max_items=config.MAX_ARTICLES_TO_PROCESS)

    if not articles:
        print("❌ Aucun nouvel article trouvé dans les flux RSS")
        return False

    print(f"✅ {len(articles)} articles trouvés")

    # Sélectionner le premier article (le plus récent)
    article = articles[0]
    print(f"📄 Article sélectionné : {article.title[:60]}...")

    # Générer un titre français
    print("🤖 Génération d'un titre français...")
    french_title = ai_generator.generate_french_title(
        title=article.title,
        source=article.source,
        summary=article.summary,
    )
    if not french_title:
        french_title = article.title

    print(f"✅ Titre généré : {french_title}")

    # Générer le texte de l'article
    print("🤖 Génération du texte de l'article...")
    breaking_text = ai_generator.generate_post(
        title=article.title,
        url=article.url,
        source=article.source,
        summary=article.summary,
    )

    if not breaking_text:
        print("❌ Échec de la génération du texte de l'article")
        return False

    print(f"✅ Texte généré : {breaking_text[:100]}...")

    # Générer un texte long pour Facebook
    print("🤖 Génération du texte long pour Facebook...")
    long_text = ai_generator.generate_long_post(
        title=article.title,
        url=article.url,
        source=article.source,
        summary=article.summary,
    )

    if not long_text:
        long_text = breaking_text

    print(f"✅ Texte long généré : {long_text[:100]}...")

    # Créer l'objet news
    news = {
        "title": french_title,
        "url": article.url,
        "source": article.source,
        "summary": article.summary,
        "breaking_text": breaking_text,
        "long_text": long_text,
        "published_at": datetime.now().isoformat(),
        "image": article.image,
    }

    # Publier sur Facebook
    print("\n📱 Publication sur Facebook...")
    facebook = facebook_client.FacebookClient()
    if not facebook.configure():
        print("❌ Échec de la configuration Facebook")
        return False

    # Obtenir une image valide pour Instagram
    image_url = facebook_client.get_valid_instagram_image(
        caption=long_text,
        user_image_url=article.image or "",
        title=article.title,
    )

    # Publier sur Facebook
    fb_success = facebook.post_to_page(
        message=long_text,
        link=article.url,
        image_url=image_url if config.DRY_RUN else ""
    )

    if fb_success:
        print("✅ Publication Facebook réussie !")
    else:
        print("❌ Publication Facebook échouée")

    # Attendre un peu entre les publications
    time.sleep(3)

    # Publier sur Instagram (si configuré)
    if config.INSTAGRAM_ACCOUNT_ID:
        print("\n📸 Publication sur Instagram...")
        ig_success = facebook.post_to_instagram(
            message=breaking_text,
            image_url=image_url
        )

        if ig_success:
            print("✅ Publication Instagram réussie !")
        else:
            print("❌ Publication Instagram échouée")
    else:
        print("\n⚠️  Instagram non configuré (INSTAGRAM_ACCOUNT_ID manquant)")
        ig_success = False

    # Marquer l'article comme traité
    database.mark_article_processed(
        url=article.url,
        title=article.title,
        source=article.source,
        post_text=breaking_text,
    )

    # Sauvegarder dans la base de données
    database.save_breaking_news(news)

    return fb_success or ig_success

def main():
    """Point d'entrée principal."""
    print("🚀 DÉMARRAGE DE LA PUBLICATION D'UN VRAI ARTICLE")
    print("=" * 60)

    # Vérification de la configuration
    print(f"Configuration actuelle :")
    print(f"  - DRY_RUN : {config.DRY_RUN}")
    print(f"  - FACEBOOK_PAGE_ID : {config.FACEBOOK_PAGE_ID}")
    print(f"  - INSTAGRAM_ACCOUNT_ID : {config.INSTAGRAM_ACCOUNT_ID or 'Non configuré'}")
    print(f"  - Token présent : {'Oui' if config.FB_PAGE_ACCESS_TOKEN else 'Non'}")

    # Attendre un peu pour éviter les problèmes de rate limiting
    time.sleep(2)

    # Publier l'article
    success = publish_real_article()

    # Résumé final
    print("\n" + "=" * 60)
    print("📊 RÉSULTATS DE LA PUBLICATION")
    print("=" * 60)

    if success:
        print("🎉 Publication de l'article réussie !")
        print("   L'article a été publié sur Facebook et/ou Instagram")
    else:
        print("⚠️  La publication de l'article a échoué")
        print("   Vérifiez les logs et la configuration")

    print("=" * 60)

if __name__ == "__main__":
    main()