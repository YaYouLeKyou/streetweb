# 🤖 Streetweb — Veille Faits Divers & Culture Urbaine

Agent IA autonome qui surveille les actualités **Faits Divers & Culture Urbaine** via des flux RSS, génère un post sensationnaliste en français optimisé par **Gemini / Groq**, et le publie automatiquement sur **Facebook** et **Instagram** — **jusqu'à 4 fois par jour** par défaut.

## ✨ Fonctionnalités

| Fonctionnalité | Détail |
|---|---|
| 📡 **Veille RSS** | 7 flux Faits Divers & Culture Urbaine (FR) scannés à chaque exécution |
| 🧠 **IA de rédaction** | Post en français, ≤ 2200 caractères, 3 hashtags ciblés (#FaitsDivers #CultureUrbaine #Street) |
| 💾 **Anti-doublons** | Base SQLite locale (`streetweb_bot.db`) — aucun article republié |
| 📘 **Facebook** | Publication automatique avec lien + résumé long |
| 📸 **Instagram** | Publication avec image unique par article (RSS ou fallback) + résumé long |
| 🕐 **Planification** | Jusqu'à 4 publications/jour aux heures fixes heure de Paris, ou par intervalle |
| 🔄 **Interface web** | Dashboard Flask pour publier maintenant, modifier les heures, changer l'intervalle |
| ⏰ **Post minute** | Publication immédiate sur les plateformes sélectionnées |
| 🔄 **Déploiement 24/7** | Web Service Render / Railway (`Procfile` inclus) |
| 🔑 **Renouvellement auto des tokens** | Vérifie et renouvelle les tokens Meta tous les 30 jours + alerte email en cas d'expiration |

## 📁 Structure du projet

```
streetweb/
├── main.py            # Orchestrateur + boucle schedule + logs
├── config.py           # Clés API, flux RSS, planification, prompts
├── database.py         # SQLite anti-doublons (streetweb_bot.db)
├── rss_parser.py       # Extraction RSS via feedparser + images
├── ai_generator.py     # Génération post via Gemini / Groq (OpenAI SDK)
├── facebook_client.py  # Publication Facebook/Instagram (Meta Graph API)
├── token_renewal.py    # Renouvellement automatique des tokens API
├── web_app.py          # Dashboard Flask + API REST
├── templates/
│   └── index.html      # Interface web
├── requirements.txt    # Dépendances Python
├── .env.example        # Modèle de variables d'environnement
├── Procfile            # worker: python main.py (Render/Railway)
├── render.yaml         # Config Blueprint Render (web service + /ping)
└── README.md
```

## 🚀 Installation locale

### 1. Prérequis
- Python 3.10+
- Clé API **Gemini** (ou Groq / OpenAI compatible)
- Page Facebook + compte Instagram Business lié

### 2. Configuration

```bash
# Clonez le projet puis :
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate    # macOS / Linux

pip install -r requirements.txt
cp .env.example .env
```

Renseignez ensuite le fichier `.env` :

| Variable | Description |
|---|---|
| `LLM_API_KEY` | Clé API LLM (Gemini / Groq / OpenAI) |
| `LLM_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` (Gemini) ou `https://api.groq.com/openai/v1` (Groq) |
| `LLM_MODEL` | `gemini-3.5-flash-lite` (Gemini) ou `groq/compound-mini` (Groq) |
| `FB_PAGE_ACCESS_TOKEN` | Page Access Token Meta (permanent, avec permissions `pages_read_engagement`, `pages_manage_posts`) |
| `FACEBOOK_PAGE_ID` | ID de la page Facebook |
| `INSTAGRAM_ACCOUNT_ID` | ID du compte Instagram Business (optionnel) |
| `FB_APP_ID` | Identifiant de l'app Facebook (pour renouvellement auto) |
| `FB_APP_SECRET` | Secret de l'app Facebook (pour renouvellement auto) |

### 3. Test rapide

```bash
# Exécute un cycle complet immédiatement (scan + génération + publication)
set TEST_ON_STARTUP=true && python main.py
```

> ⚠️ Avec `TEST_ON_STARTUP=true`, un post sera publié **dès le lancement**.
> Mettez-le à `false` pour que le premier post parte à l'heure planifiée.

## 🧪 Mode simulation (Dry-Run) — Recommandé pour tester

Le mode **Dry-Run** exécute tout le code (récupération RSS + appel au LLM)
mais **affiche le post dans la console VS Code au lieu de l'envoyer à Facebook/Instagram**.

### Activation

Dans `.env` :

```env
DRY_RUN=true
```

### Comportement

| Paramètre | Valeur | Effet |
|---|---|---|
| `DRY_RUN=true` | 🧪 Simulation | Le post est affiché dans la console, **rien n'est publié** |
| `DRY_RUN=false` | 📘📸 Publication réelle | Le post est envoyé sur Facebook et Instagram (comportement normal) |

### Exemple de sortie console

```
============================================================
MODE TEST (DRY RUN) — POST FACEBOOK NON ENVOYÉ
============================================================
Page ID : 123456789
Message : Un braquage spectaculaire a eu lieu cette nuit...
Lien    : https://www.leparisien.fr/faits-divers/...
============================================================
```

### Utilisation recommandée

1. **Tant que `DRY_RUN=true`**, lancez le script autant de fois que nécessaire
   pour ajuster les prompts et vérifier la qualité des résumés **sans toucher à Facebook/Instagram**.
2. **Passez à `DRY_RUN=false`** uniquement quand vous êtes satisfait du résultat.
3. **Combinez avec `TEST_ON_STARTUP=true`** pour tester immédiatement sans attendre
   l'heure planifiée :

```env
DRY_RUN=true
TEST_ON_STARTUP=true
```

```bash
python main.py
```

> ✅ **Avantage** : aucun post réel publié, aucun quota API consommé,
> et vous pouvez itérer sur vos prompts en toute sécurité.

## ⏰ Planification

Le bot publie automatiquement aux **heures fixes** ou par **intervalle** :

| Mode | Défaut | Détail |
|---|---|---|
| 🕐 **Heures fixes** | **07:00, 12:00, 17:00, 20:00 heure de Paris** | Jusqu'à 4 publications/jour aux heures définies |
| 🔄 **Intervalle** | Désactivé par défaut | Publications supplémentaires toutes les N heures |

### Configuration

Dans `.env` :

```env
# Heures fixes (heure de Paris)
SCHEDULE_TIMES=07:00,12:00,17:00,20:00

# Intervalle (0 = désactivé, sinon toutes les N heures)
NEWS_INTERVAL_HOURS=0
```

### Interface web

Le dashboard permet de :
- Modifier les heures de publication (jusqu'à 4)
- Activer/désactiver le mode intervalle
- Publier immédiatement sur Facebook et/ou Instagram

## ⏰ Compatibilité plan gratuit Render — Garantie 4 posts/jour

Le plan **gratuit** de Render met le service en veille après 15 minutes d'inactivité.
Pour garantir vos **4 publications automatiques par jour**, le projet inclut un
endpoint `/ping` qui réveille le service et exécute les posts planifiés.

### Fonctionnement

| Élément | Détail |
|---|---|
| **Endpoint `/ping`** | Route Flask intégrée dans `web_app.py` qui réveille le service et appelle `schedule.run_pending()` |
| **Cron externe gratuit** | Un service comme cron-job.org ou UptimeRobot ping `https://VOTRE-APP.onrender.com/ping` toutes les 5-10 minutes |
| **Résultat** | Les 4 posts (07:00, 12:00, 17:00, 20:00 heure de Paris) sont publiés dans les 10 minutes max après l'heure cible |

### Configuration avec cron-job.org (gratuit)

1. Créez un compte gratuit sur [cron-job.org](https://cron-job.org)
2. Cliquez sur **+ Create cronjob**
3. Configurez :
   - **URL** : `https://VOTRE-APP.onrender.com/ping`
   - **Schedule** : Every 5 minutes (ou 10 minutes maximum)
   - **Enabled** : ✅
4. Sauvegardez — c'est tout !

### Alternative : UptimeRobot

1. Créez un compte gratuit sur [uptimerobot.com](https://uptimerobot.com)
2. **Add New Monitor** → HTTP(s) Monitor
3. **URL** : `https://VOTRE-APP.onrender.com/ping`
4. **Interval** : 5 minutes
5. Sauvegardez

> 💡 **Remarque** : si le service est déjà réveillé (plan Starter), l'endpoint `/ping`
> n'a pas d'effet visible — il vérifie simplement si un post est dû et continue.

## 🔑 Renouvellement automatique des tokens API

Les tokens Meta (Facebook, Instagram) expirent après **60 jours**. Ce projet
inclut un système de renouvellement automatique qui garantit que votre application
**ne perd jamais l'accès** aux API.

### Fonctionnement

| Événement | Action |
|---|---|
| **Au démarrage** | Vérifie la validité des tokens Facebook et Instagram |
| **Tous les 30 jours** (configurable) | Renouvelle les tokens pour leur redonner 60 jours de validité |
| **Token expiré/invalide** | Envoie une **notification email** à `ALERT_EMAIL` |
| **Renouvellement réussi** | Envoie un email de confirmation avec le nouveau token |

### Configuration

Dans `.env` :

```env
# Identifiants de l'application Facebook (nécessaires pour fb_exchange_token)
# https://developers.facebook.com/apps/ → votre app → Paramètres → Identifiants
FB_APP_ID=
FB_APP_SECRET=

# Nombre de jours entre deux renouvellements (défaut : 30)
TOKEN_RENEWAL_DAYS=30
```

### Utilisation manuelle

```bash
# Vérification seule (sans renouvellement)
python token_renewal.py --check

# Vérification + renouvellement
python token_renewal.py
```

### Notifications email

Pour activer les alertes email, configurez dans `.env` :

```env
SMTP_ENABLED=true
ALERT_EMAIL=votre@email.com
SMTP_HOST=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_TLS=true
SMTP_USERNAME=votre@email.com
SMTP_PASSWORD=votre_mot_de_passe
```

> ⚠️ **Important** : pour que le renouvellement Facebook fonctionne, vous devez
> renseigner `FB_APP_ID` et `FB_APP_SECRET` (disponibles sur
> [developers.facebook.com](https://developers.facebook.com/apps/)).
> Sans ces identifiants, le script vérifie le token mais ne peut pas le renouveler.

## 🌐 Déploiement continu (Render / Railway)

### Option 1 — Render (Web Service) ✅ Recommandé

Le fichier `render.yaml` configure tout automatiquement via **Blueprint** :

1. Poussez le projet sur **GitHub**
2. Sur [Render](https://render.com) : **New → Blueprint**
3. Sélectionnez votre dépôt — le service web est créé automatiquement
4. Renseignez les variables d'environnement dans le dashboard (les clés marquées `sync: false`)

Variables à renseigner manuellement dans le dashboard Render :
`LLM_API_KEY`, `FB_PAGE_ACCESS_TOKEN`, `FACEBOOK_PAGE_ID`,
`INSTAGRAM_ACCOUNT_ID`, `FB_APP_ID`, `FB_APP_SECRET`

### Option 2 — Railway

```bash
# 1. Poussez le projet sur GitHub
# 2. Sur Railway : New Project → Deploy from GitHub
# 3. Configurez un service de type "Worker" :
#    Build Command :  pip install -r requirements.txt
#    Start Command :  python main.py
# 4. Ajoutez les variables d'environnement (mêmes clés que .env)
```

Le `Procfile` (`worker: python main.py`) est reconnu automatiquement
par Railway comme service worker.

### Logs sur le dashboard

Le bot produit des logs clairs et horodatés :

```
2026-08-19 21:30:01 | INFO | streetweb-agent | === Début du cycle de veille ===
2026-08-19 21:30:03 | INFO | rss_parser    | Total : 24 articles collectés depuis 7 flux
2026-08-19 21:30:03 | INFO | rss_parser    | 5 nouveaux articles (non encore publiés)
2026-08-19 21:30:05 | INFO | streetweb-agent | Article sélectionné : « … »
2026-08-19 21:30:08 | INFO | ai_generator  | Post généré (198 caractères)
2026-08-19 21:30:10 | INFO | facebook_client| Post Facebook publié avec succès — ID : 123456789
2026-08-19 21:30:12 | INFO | facebook_client| Post Instagram publié avec succès — ID : 987654321
```

## 📡 Flux RSS Faits Divers & Culture Urbaine intégrés

| Source | Flux |
|---|---|
| Le Parisien 🇫🇷 | `https://www.leparisien.fr/faits-divers/rss.xml` |
| 20 Minutes 🇫🇷 | `https://www.20minutes.fr/faits-divers/rss.xml` |
| BFMTV 🇫🇷 | `https://www.bfmtv.com/faits-divers/rss.xml` |
| France Info 🇫🇷 | `https://www.francetvinfo.fr/faits-divers/rss.xml` |
| Booska-P 🇫🇷 | `https://www.booska-p.com/feed/` |
| Rap2France 🇫🇷 | `https://www.rap2france.com/feed/` |
| Le Monde Culture 🇫🇷 | `https://www.lemonde.fr/culture/rss.xml` |

Personnalisation dans `.env` :

```env
RSS_FEED_URLS=https://feed1.com/feed/,https://feed2.com/feed/
```

## 🗄️ Base de données anti-doublons

Le fichier `streetweb_bot.db` (SQLite) est créé automatiquement au premier lancement.
Il stocke chaque URL traitée — garantissant **aucune republication** d'une même
actualité, même si le flux re-propose l'article plus tard.

## 📝 Notes techniques

- **Limite post** : 2200 caractères générés par l'IA (limite de sécurité Facebook/Instagram)
- **Anti-échec** : si un article échoue à la génération IA, il est marqué « traité »
  pour ne pas bloquer indéfiniment le worker
- **Troncature intelligente** : si le post dépasse 2200 caractères, le script
  conserve l'accroche + le lien + les hashtags
