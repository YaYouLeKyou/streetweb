"""
Script de diagnostic et test de la publication Facebook.

Usage :
    python test_facebook.py

Ce script :
  1. Vérifie la validité du token (debug_token)
  2. Récupère l'ID de page associé au token (/me)
  3. Compare avec le FACEBOOK_PAGE_ID configuré
  4. Tente une publication de test sur la page avec logs détaillés
"""

import logging
import sys

import requests

import config
import facebook_client

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("test-facebook")

GRAPH_API_URL = "https://graph.facebook.com/v19.0"


def check_config() -> None:
    """Vérifie la présence des variables de configuration."""
    print("\n" + "=" * 60)
    print("1️⃣  CONFIGURATION")
    print("=" * 60)
    print(f"FB_PAGE_ACCESS_TOKEN   : {'✅ défini (' + config.FB_PAGE_ACCESS_TOKEN[:25] + '...)' if config.FB_PAGE_ACCESS_TOKEN else '❌ MANQUANT'}")
    print(f"FACEBOOK_PAGE_ID    : {config.FACEBOOK_PAGE_ID or '❌ MANQUANT'}")
    print(f"DRY_RUN             : {config.DRY_RUN}")


def test_token_validity() -> dict:
    """Vérifie la validité du token via debug_token."""
    print("\n" + "=" * 60)
    print("2️⃣  VALIDITÉ DU TOKEN (/debug_token)")
    print("=" * 60)

    facebook = facebook_client.FacebookClient()
    token_info = facebook.check_token()

    if not token_info:
        print("❌ Impossible de vérifier le token (erreur réseau)")
        return {}

    print(f"is_valid      : {token_info.get('is_valid')}")
    print(f"type          : {token_info.get('type')}")
    print(f"scopes        : {token_info.get('scopes')}")
    print(f"permissions manquantes : {token_info.get('missing_scopes') or 'aucune'}")
    if token_info.get("expires_at"):
        import datetime
        exp = datetime.datetime.fromtimestamp(token_info["expires_at"])
        print(f"expiration    : {exp.strftime('%d/%m/%Y %H:%M')}")
    print(f"user_id       : {token_info.get('user_id')}")
    return token_info


def test_page_matching() -> None:
    """Vérifie que le FACEBOOK_PAGE_ID correspond à la page du token."""
    print("\n" + "=" * 60)
    print("3️⃣  CORRESPONDANCE TOKEN ↔ PAGE")
    print("=" * 60)

    # Récupère l'ID associé au token via /me
    try:
        response = requests.get(
            f"{GRAPH_API_URL}/me",
            params={"access_token": config.FB_PAGE_ACCESS_TOKEN},
            timeout=30,
        )
        data = response.json()
        print(f"GET /me → {response.status_code} : {data}")

        if response.status_code == 200:
            token_entity_id = str(data.get("id"))
            token_entity_name = data.get("name", "?")

            configured_page_id = str(config.FACEBOOK_PAGE_ID)

            if token_entity_id == configured_page_id:
                print(f"✅ Le token appartient à la page configurée : {token_entity_name} (ID {token_entity_id})")
            else:
                print(f"❌ MISMATCH !")
                print(f"   - Page du token (/me)    : {token_entity_name} (ID {token_entity_id})")
                print(f"   - Page configurée (.env) : ID {configured_page_id}")
                print(f"   → Corrigez FACEBOOK_PAGE_ID dans .env avec {token_entity_id}")

        else:
            error = data.get("error", {})
            print(f"❌ Erreur /me : {error.get('code')} — {error.get('message')}")

    except Exception as exc:  # noqa: BLE001
        print(f"❌ Exception : {exc}")


def test_page_info() -> None:
    """Récupère les infos de la page configurée."""
    print("\n" + "=" * 60)
    print("4️⃣  INFOS DE LA PAGE CONFIGURÉE")
    print("=" * 60)

    try:
        response = requests.get(
            f"{GRAPH_API_URL}/{config.FACEBOOK_PAGE_ID}",
            params={
                "access_token": config.FB_PAGE_ACCESS_TOKEN,
                "fields": "id,name,about,fan_count,link",
            },
            timeout=30,
        )
        data = response.json()
        print(f"GET /{config.FACEBOOK_PAGE_ID} → {response.status_code}")

        if response.status_code == 200:
            print(f"Nom    : {data.get('name')}")
            print(f"ID     : {data.get('id')}")
            print(f"Fans   : {data.get('fan_count')}")
            print(f"Lien   : {data.get('link')}")
            print("✅ La page est accessible avec le token")
        else:
            error = data.get("error", {})
            print(f"❌ Erreur : {error.get('code')} — {error.get('message')}")
            print("   → Le token n'a pas accès à cette page !")
            print("   → Vérifiez que FACEBOOK_PAGE_ID est bien l'ID de la page gérée par ce token.")

    except Exception as exc:  # noqa: BLE001
        print(f"❌ Exception : {exc}")


def test_instagram_account() -> None:
    """Vérifie si un compte Instagram est associé à la page Facebook."""
    print("\n" + "=" * 60)
    print("5️⃣  COMPTE INSTAGRAM ASSOCIÉ")
    print("=" * 60)

    if not config.INSTAGRAM_ACCOUNT_ID:
        print("INSTAGRAM_ACCOUNT_ID : ❌ non configuré dans .env")
    else:
        print(f"INSTAGRAM_ACCOUNT_ID : {config.INSTAGRAM_ACCOUNT_ID}")

    # Essaie de récupérer le compte Instagram associé à la page
    try:
        response = requests.get(
            f"{GRAPH_API_URL}/{config.FACEBOOK_PAGE_ID}",
            params={
                "access_token": config.FB_PAGE_ACCESS_TOKEN,
                "fields": "id,name,instagram_business_account",
            },
            timeout=30,
        )
        data = response.json()
        print(f"GET /{config.FACEBOOK_PAGE_ID}?fields=instagram_business_account → {response.status_code}")

        if response.status_code == 200:
            ig_account = data.get("instagram_business_account")
            if ig_account:
                print(f"✅ Compte Instagram associé : ID={ig_account.get('id')} username={ig_account.get('username')}")
                if not config.INSTAGRAM_ACCOUNT_ID:
                    print(f"   → Ajoutez INSTAGRAM_ACCOUNT_ID={ig_account.get('id')} dans .env")
            else:
                print("❌ Aucun compte Instagram associé à cette page Facebook")
                print("   → Connectez un compte Instagram à la page dans Meta Business Suite")
        else:
            error = data.get("error", {})
            print(f"❌ Erreur : {error.get('code')} — {error.get('message')}")

    except Exception as exc:  # noqa: BLE001
        print(f"❌ Exception : {exc}")


def test_post() -> None:
    """Tente une publication de test."""
    print("\n" + "=" * 60)
    print("6️⃣  PUBLICATION DE TEST FACEBOOK")
    print("=" * 60)

    facebook = facebook_client.FacebookClient()
    if not facebook.configure():
        print("❌ Configuration Facebook échouée")
        return

    test_message = "🧪 Test de publication depuis l'interface de veille — ceci est un test technique."
    print(f"Message de test : {test_message}")
    print(f"URL de publication : {GRAPH_API_URL}/{config.FACEBOOK_PAGE_ID}/feed")

    # Publication réelle
    success = facebook.post_to_page(message=test_message)
    if success:
        print("✅ Publication de test RÉUSSIE !")
    else:
        print("❌ Publication de test ÉCHOUÉE (voir logs ci-dessus)")


def test_post_instagram() -> None:
    """Tente une publication de test sur Instagram."""
    print("\n" + "=" * 60)
    print("7️⃣  PUBLICATION DE TEST INSTAGRAM")
    print("=" * 60)

    if not config.INSTAGRAM_ACCOUNT_ID:
        print("❌ INSTAGRAM_ACCOUNT_ID non configuré — impossible de tester Instagram")
        return

    facebook = facebook_client.FacebookClient()
    if not facebook.configure():
        print("❌ Configuration Facebook échouée")
        return

    test_message = "🧪 Test de publication Instagram depuis l'interface de veille."
    print(f"Message de test : {test_message}")
    print(f"Instagram Account ID : {config.INSTAGRAM_ACCOUNT_ID}")

    # Publication réelle
    success = facebook.post_to_instagram(message=test_message)
    if success:
        print("✅ Publication Instagram de test RÉUSSIE !")
    else:
        print("❌ Publication Instagram de test ÉCHOUÉE (voir logs ci-dessus)")


def main() -> None:
    """Point d'entrée principal du test."""
    print("🔍 DIAGNOSTIC FACEBOOK — DÉMARRAGE")
    check_config()
    if not config.FB_PAGE_ACCESS_TOKEN:
        print("\n❌ FB_PAGE_ACCESS_TOKEN manquant — impossible de continuer.")
        return

    test_token_validity()
    test_page_matching()
    test_page_info()
    test_instagram_account()
    test_post()
    test_post_instagram()

    print("\n" + "=" * 60)
    print("✅ DIAGNOSTIC TERMINÉ")
    print("=" * 60)


if __name__ == "__main__":
    main()