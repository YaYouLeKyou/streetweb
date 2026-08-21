"""
Script de test de publication IMMEDIATE sur Facebook/Instagram.
Bypasse le scraping RSS et le scheduler : prend le dernier post en base
et le publie directement via l'API Meta.

Usage :
    python test_publish.py              # publie sur Facebook + Instagram
    python test_publish.py --network facebook   # Facebook seulement
    python test_publish.py --network instagram  # Instagram seulement
    python test_publish.py --dry-run            # simulation sans publication
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import database
import facebook_client
import news_service
from web_app import _build_long_post_message


def force_publish(networks: list[str], dry_run: bool = False) -> bool:
    """Publie le dernier post de la base sur les réseaux demandés."""
    if dry_run:
        config.DRY_RUN = True

    latest = news_service.get_latest_news()
    if not latest:
        print("ERREUR : Aucun post disponible en base.")
        print("Lancez d'abord : python main.py (attendez la generation) ou utilisez /api/refresh")
        return False

    print(f"Post a publier : {latest.get('title', '')[:80]}")
    print(f"Reseaux : {', '.join(networks)}")
    print(f"Mode dry-run : {dry_run}")
    print("-" * 60)

    success = False

    if "facebook" in networks:
        print("Publication Facebook...")
        fb = facebook_client.FacebookClient()
        if not fb.configure():
            print("ERREUR : Configuration Facebook echouee (token invalide ?)")
            return False

        message = latest.get("long_text") or _build_long_post_message(latest)
        raw_image = latest.get("image") or ""
        image_url = facebook_client.get_valid_instagram_image(
            caption=latest.get("breaking_text", ""),
            user_image_url=raw_image,
            title=latest.get("title", ""),
        )

        published = fb.post_to_page(
            message=message,
            link=latest.get("url", ""),
            image_url=image_url,
        )
        if published:
            print(f"OK - Post Facebook publie (ID: {latest.get('id')})")
            success = True
        else:
            print("ERREUR : Publication Facebook echouee")

    if "instagram" in networks:
        print("Publication Instagram...")
        fb = facebook_client.FacebookClient()
        if not fb.configure():
            print("ERREUR : Configuration Instagram echouee (token invalide ?)")
            return False

        message = latest.get("long_text") or _build_long_post_message(latest)
        raw_image = latest.get("image") or ""
        image_url = facebook_client.get_valid_instagram_image(
            caption=latest.get("breaking_text", ""),
            user_image_url=raw_image,
            title=latest.get("title", ""),
        )

        published = fb.post_to_instagram(
            message=message,
            image_url=image_url,
        )
        if published:
            print(f"OK - Post Instagram publie (ID: {latest.get('id')})")
            success = True
        else:
            print("ERREUR : Publication Instagram echouee")

    print("-" * 60)
    if success:
        print("SUCCES : Au moins un reseau a ete publie.")
    else:
        print("ECHEC : Aucune publication reussie.")
    return success


def main() -> None:
    parser = argparse.ArgumentParser(description="Publication forcee Streetweb")
    parser.add_argument(
        "--network",
        nargs="+",
        choices=["facebook", "instagram"],
        default=["facebook", "instagram"],
        help="Reseaux cibles (defaut: facebook instagram)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simule la publication sans envoyer reellement",
    )
    args = parser.parse_args()

    ok = force_publish(networks=args.network, dry_run=args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
