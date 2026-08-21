#!/usr/bin/env python3
"""
Script de test pour publier des posts de test sur Facebook et Instagram en mode DRY_RUN.

Usage :
    python test_social_media_posts_dryrun.py

Ce script :
  1. Active le mode DRY_RUN (simulation)
  2. Teste la publication sur Facebook (sans publication réelle)
  3. Teste la publication sur Instagram (sans publication réelle)
  4. Affiche les résultats détaillés
"""

import logging
import sys
import time
from datetime import datetime

import config
import facebook_client

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("test-social-posts-dryrun")

def create_test_post_message():
    """Crée un message de test avec horodatage."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"🧪 Test de publication automatique — {timestamp} — Ceci est un test technique pour vérifier le bon fonctionnement du système de publication."

def create_test_instagram_message():
    """Crée un message de test pour Instagram avec horodatage."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"🧪 Test Instagram — {timestamp} — Vérification du système de publication automatique. #Test #Streetweb #Technique"

def test_facebook_post():
    """Teste la publication sur Facebook en mode DRY_RUN."""
    print("\n" + "=" * 60)
    print("📱 TEST DE PUBLICATION FACEBOOK (MODE DRY_RUN)")
    print("=" * 60)

    facebook = facebook_client.FacebookClient()
    if not facebook.configure():
        print("❌ Échec de la configuration Facebook")
        return False

    test_message = create_test_post_message()
    print(f"Message : {test_message}")
    print(f"Mode DRY_RUN : {config.DRY_RUN}")

    # Publication sur Facebook (en mode DRY_RUN, rien ne sera réellement publié)
    success = facebook.post_to_page(message=test_message)

    if success:
        print("✅ Test Facebook réussi (mode simulation) !")
        return True
    else:
        print("❌ Test Facebook échoué")
        return False

def test_instagram_post():
    """Teste la publication sur Instagram en mode DRY_RUN."""
    print("\n" + "=" * 60)
    print("📸 TEST DE PUBLICATION INSTAGRAM (MODE DRY_RUN)")
    print("=" * 60)

    if not config.INSTAGRAM_ACCOUNT_ID:
        print("❌ INSTAGRAM_ACCOUNT_ID non configuré")
        return False

    facebook = facebook_client.FacebookClient()
    if not facebook.configure():
        print("❌ Échec de la configuration Facebook")
        return False

    test_message = create_test_instagram_message()
    print(f"Message : {test_message}")
    print(f"Mode DRY_RUN : {config.DRY_RUN}")

    # Utiliser une image de fallback pour le test
    image_url = "https://images.unsplash.com/photo-1493225255756-d9584f8606e9?w=1080&h=1080&fit=crop"

    # Publication sur Instagram (en mode DRY_RUN, rien ne sera réellement publié)
    success = facebook.post_to_instagram(message=test_message, image_url=image_url)

    if success:
        print("✅ Test Instagram réussi (mode simulation) !")
        return True
    else:
        print("❌ Test Instagram échoué")
        return False

def main():
    """Point d'entrée principal."""
    print("🚀 DÉMARRAGE DES TESTS EN MODE DRY_RUN")
    print("=" * 60)

    # Activer le mode DRY_RUN pour ce test
    original_dry_run = config.DRY_RUN
    config.DRY_RUN = True
    print(f"Mode DRY_RUN activé : {config.DRY_RUN}")

    # Vérification de la configuration
    print(f"Configuration actuelle :")
    print(f"  - FACEBOOK_PAGE_ID : {config.FACEBOOK_PAGE_ID}")
    print(f"  - INSTAGRAM_ACCOUNT_ID : {config.INSTAGRAM_ACCOUNT_ID or 'Non configuré'}")
    print(f"  - Token présent : {'Oui' if config.FB_PAGE_ACCESS_TOKEN else 'Non'}")
    print("\n⚠️  AUCUNE PUBLICATION RÉELLE NE SERA EFFECTUÉE (mode simulation)")

    # Attendre un peu pour éviter les problèmes de rate limiting
    time.sleep(2)

    # Test Facebook
    fb_success = test_facebook_post()

    # Attendre entre les tests pour éviter les problèmes
    time.sleep(3)

    # Test Instagram
    ig_success = test_instagram_post()

    # Résumé final
    print("\n" + "=" * 60)
    print("📊 RÉSULTATS DES TESTS (MODE DRY_RUN)")
    print("=" * 60)
    print(f"Facebook : {'✅ Réussi' if fb_success else '❌ Échoué'}")
    print(f"Instagram : {'✅ Réussi' if ig_success else '❌ Échoué'}")

    if fb_success and ig_success:
        print("\n🎉 Tous les tests en mode simulation ont réussi !")
        print("   Vous pouvez maintenant désactiver DRY_RUN pour des publications réelles.")
    else:
        print("\n⚠️ Certains tests ont échoué. Vérifiez les logs et la configuration.")

    # Restaurer la valeur originale
    config.DRY_RUN = original_dry_run
    print(f"Mode DRY_RUN restauré : {config.DRY_RUN}")

    print("=" * 60)

if __name__ == "__main__":
    main()