# Exemple Complet : Configuration d'un Notifier pour les Incidents

> Guide pas à pas pour configurer IMAS Manager avec un notifier Slack qui se déclenche automatiquement lors de la création d'un incident.

---

## 📋 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Prérequis](#prérequis)
3. [Étape 1 : Créer une Team](#étape-1--créer-une-team)
4. [Étape 2 : Créer un Service](#étape-2--créer-un-service)
5. [Étape 3 : Configurer le Notification Provider](#étape-3--configurer-le-notification-provider)
6. [Étape 4 : Créer un Incident (Test)](#étape-4--créer-un-incident-test)
7. [Vérification du Workflow](#vérification-du-workflow)
8. [Variantes de Configuration](#variantes-de-configuration)

---

## Vue d'ensemble

### Workflow Complet

Voici le flux qui se déclenche lors de la création d'un incident :

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CRÉATION D'UN INCIDENT                             │
│                    (Dashboard, API, ou Webhook d'alerte)                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         IncidentOrchestrator                                 │
│                                                                             │
│  1. Crée l'objet Incident en base                                           │
│  2. Déclenche la tâche Celery `setup_incident_task`                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      setup_incident_task (Celery)                            │
│                                                                             │
│  Exécute en parallèle :                                                      │
│  ├── 📄 Création du LID (Google Doc)                                         │
│  ├── 💬 Création War Room (si SEV1/SEV2)                                     │
│  └── 📢 NotificationRouter.route_incident()                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NotificationRouter                                   │
│                                                                             │
│  Calcule les destinataires :                                                 │
│  ├── Canal Slack de l'équipe propriétaire du service                        │
│  ├── Personne d'astreinte (On-Call)                                          │
│  └── Emails des ImpactScopes (si configurés)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NotificationProviderFactory                               │
│                                                                             │
│  Instancie le provider approprié (Slack, Discord, Email, SMS...)            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Slack Provider                                      │
│                                                                             │
│  Envoie le message formaté avec :                                            │
│  - Titre, Sévérité, Statut                                                   │
│  - Lien Dashboard, Runbook, LID, War Room                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Prérequis

Avant de commencer, assurez-vous d'avoir :

- [ ] IMAS Manager déployé et fonctionnel
- [ ] Accès admin à l'interface Django (`/admin/`)
- [ ] Une App Slack créée (voir [Créer une App Slack](#créer-une-app-slack))
- [ ] Celery et Redis configurés (pour les tâches asynchrones)

### Créer une App Slack

1. Allez sur [api.slack.com/apps](https://api.slack.com/apps)
2. Cliquez sur **Create New App** → **From scratch**
3. Donnez un nom (ex: `IMAS Manager`) et sélectionnez votre workspace
4. Dans **OAuth & Permissions**, ajoutez les scopes suivants :
   - `chat:write` - Envoyer des messages
   - `channels:read` - Lire les infos des canaux
5. Cliquez sur **Install to Workspace**
6. Copiez le **Bot User OAuth Token** (commence par `xoxb-`)

---

## Étape 1 : Créer une Team

La Team représente l'équipe responsable des services. C'est elle qui sera notifiée lors d'un incident.

### Via l'Admin Django

1. Accédez à : `https://imas.example.com/admin/core/team/add/`
2. Remplissez les champs :

| Champ | Valeur | Description |
|-------|--------|-------------|
| **Name** | `SRE Core` | Nom de votre équipe |
| **Slack Channel ID** | `C0123456789` | ID du canal Slack de l'équipe (ex: #sre-core) |
| **Current On-Call** | (sélectionner un utilisateur) | Personne à notifier en priorité |

3. Cliquez sur **Save**

### Trouver l'ID d'un Canal Slack

1. Dans Slack, faites clic droit sur le canal
2. **View channel details** → **Copy channel ID** (en bas)

> 💡 L'ID ressemble à `C0123456789` (commence par C pour les canaux publics)

---

## Étape 2 : Créer un Service

Le Service représente le composant technique qui peut être affecté par un incident.

### Via l'Admin Django

1. Accédez à : `https://imas.example.com/admin/core/service/add/`
2. Remplissez les champs :

| Champ | Valeur | Description |
|-------|--------|-------------|
| **Name** | `redis-prod` | Nom technique du service |
| **Owner Team** | `SRE Core` | L'équipe créée à l'étape 1 |
| **Criticality** | `TIER_1_CRITICAL` | Niveau de criticité |
| **Runbook URL** | `https://wiki.example.com/runbooks/redis` | Lien vers la documentation |

3. Cliquez sur **Save**

---

## Étape 3 : Configurer le Notification Provider

C'est ici que vous configurez le provider Slack pour envoyer les notifications.

### Via l'Admin Django

1. Accédez à : `https://imas.example.com/admin/core/notificationprovider/add/`
2. Remplissez les champs :

| Champ | Valeur |
|-------|--------|
| **Name** | `Slack Production` |
| **Type** | `SLACK` |
| **Is Active** | ✅ Coché |
| **Config** | Voir ci-dessous |

### Configuration JSON pour Slack

```json
{
  "bot_token": "xoxb-1234567890-1234567890123-abcdefghijklmnopqrstuvwx",
  "default_channel": "C0123456789"
}
```

| Clé | Description |
|-----|-------------|
| `bot_token` | Le token OAuth de votre bot Slack (récupéré dans les prérequis) |
| `default_channel` | ID du canal par défaut pour les notifications globales (optionnel) |

3. Cliquez sur **Save**

### ⚠️ Vérification

- Assurez-vous que le bot Slack est **invité dans le canal** de l'équipe
- Dans Slack, tapez `/invite @IMAS Manager` dans le canal #sre-core

---

## Étape 4 : Créer un Incident (Test)

Maintenant, testons le workflow complet en créant un incident.

### Option A : Via le Dashboard

1. Accédez à : `https://imas.example.com/dashboard/incidents/create/`
2. Remplissez le formulaire :

| Champ | Valeur |
|-------|--------|
| **Title** | `[TEST] Redis Cluster Down` |
| **Description** | `Test de notification - connexion timeout sur tous les nœuds` |
| **Service** | `redis-prod` |
| **Severity** | `SEV2_HIGH` |

3. Cliquez sur **Create Incident**

### Option B : Via l'API

```bash
# 1. Obtenir un token d'authentification
TOKEN=$(curl -s -X POST https://imas.example.com/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}' | jq -r '.token')

# 2. Récupérer l'ID du service
SERVICE_ID=$(curl -s -X GET "https://imas.example.com/api/v1/services/?search=redis-prod" \
  -H "Authorization: Token $TOKEN" | jq -r '.results[0].id')

# 3. Créer l'incident
curl -X POST https://imas.example.com/api/v1/incidents/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "[TEST] Redis Cluster Down",
    "description": "Test de notification - connexion timeout sur tous les nœuds",
    "service": "'$SERVICE_ID'",
    "severity": "SEV2_HIGH"
  }'
```

### Option C : Via Python

```python
from services.orchestrator import IncidentOrchestrator
from core.models import Service
from django.contrib.auth import get_user_model

User = get_user_model()

# Récupérer les objets nécessaires
service = Service.objects.get(name="redis-prod")
user = User.objects.get(username="admin")

# Créer l'incident
orchestrator = IncidentOrchestrator()
incident = orchestrator.create_incident(
    data={
        "title": "[TEST] Redis Cluster Down",
        "description": "Test de notification - connexion timeout sur tous les nœuds",
        "service": service,
        "severity": "SEV2_HIGH",
    },
    user=user,
    trigger_orchestration=True  # Active le workflow de notification
)

print(f"Incident créé: {incident.short_id}")
```

---

## Vérification du Workflow

### 1. Vérifier la Notification Slack

Après la création de l'incident, vous devriez voir un message dans le canal Slack de l'équipe :

```
┌─────────────────────────────────────────────────────────────┐
│ 🟠 [TEST] Redis Cluster Down - redis-prod                  │
├─────────────────────────────────────────────────────────────┤
│ Severity: SEV2_HIGH      │    Service: redis-prod          │
│ Status: TRIGGERED        │    Team: SRE Core               │
├─────────────────────────────────────────────────────────────┤
│ Description:                                                │
│ Test de notification - connexion timeout sur tous les nœuds │
├─────────────────────────────────────────────────────────────┤
│ Quick Links:                                                │
│ • 📄 LID Document                                           │
│ • 📋 Runbook                                                │
│ • 💬 War Room                                               │
├─────────────────────────────────────────────────────────────┤
│ [🔍 View Incident]                                          │
└─────────────────────────────────────────────────────────────┘
```

### 2. Vérifier les Logs

```bash
# Docker
docker logs imas_worker -f | grep -i notification

# Local
tail -f logs/celery.log | grep -i notification
```

Vous devriez voir :

```
INFO - Created incident INC-A1B2C3: [TEST] Redis Cluster Down
INFO - Sending notification to Slack channel C0123456789
INFO - Slack notification sent successfully
```

### 3. Vérifier la Timeline de l'Incident

Dans le dashboard, ouvrez l'incident et vérifiez la timeline :

| Timestamp | Type | Message |
|-----------|------|---------|
| 14:30:00 | `ALERT_SENT` | Notification sent to Slack (SRE Core) |
| 14:30:01 | `DOCUMENT_CREATED` | LID document created |

---

## Variantes de Configuration

### Exemple avec Discord (Webhook)

```json
{
  "webhook_url": "https://discord.com/api/webhooks/1234567890/abcdefghijklmnop"
}
```

### Exemple avec Email (SMTP)

```json
{
  "host": "smtp.gmail.com",
  "port": 587,
  "username": "alerts@example.com",
  "password": "your-app-password",
  "use_tls": true,
  "from_email": "IMAS Manager <incidents@example.com>"
}
```

### Exemple avec Webhook Générique (PagerDuty, Opsgenie)

```json
{
  "url": "https://events.pagerduty.com/v2/enqueue",
  "format": "pagerduty",
  "routing_key": "your-routing-key"
}
```

### Exemple avec ntfy (Push Mobile)

```json
{
  "server": "https://ntfy.sh",
  "topic": "imas-alerts",
  "priority": "high"
}
```

---

## Récapitulatif

| Étape | Action | Résultat |
|-------|--------|----------|
| 1 | Créer une Team | Équipe `SRE Core` avec canal Slack |
| 2 | Créer un Service | Service `redis-prod` rattaché à l'équipe |
| 3 | Configurer le Provider | Provider Slack actif avec token |
| 4 | Créer un Incident | Notification envoyée automatiquement |

### Diagramme Final

```
┌──────────────┐     owns      ┌──────────────┐
│   Team       │◄──────────────│   Service    │
│  SRE Core    │               │  redis-prod  │
│  #slack-ch   │               │              │
└──────────────┘               └──────────────┘
       │                              │
       │ notified via                 │ triggers
       ▼                              ▼
┌──────────────┐               ┌──────────────┐
│   Provider   │◄──────────────│   Incident   │
│ Slack Prod   │   routes to   │  INC-A1B2C3  │
│  xoxb-...    │               │  SEV2_HIGH   │
└──────────────┘               └──────────────┘
       │
       │ sends
       ▼
┌──────────────────────────────────────────┐
│           Slack Message                  │
│  🟠 [TEST] Redis Cluster Down            │
│  Service: redis-prod | SEV2_HIGH         │
└──────────────────────────────────────────┘
```

---

## Dépannage

### La notification n'est pas envoyée

1. **Vérifiez que le provider est actif** : `is_active = True`
2. **Vérifiez le token Slack** : Testez avec `curl`
3. **Vérifiez que Celery fonctionne** : `docker ps | grep worker`
4. **Consultez les logs** : `docker logs imas_worker`

### Erreur "channel_not_found"

- Le bot n'est pas invité dans le canal
- Invitez-le avec `/invite @IMAS Manager`

### Erreur "invalid_auth"

- Le token Slack est invalide ou expiré
- Régénérez le token dans l'App Slack

---

## Prochaines Étapes

- 📖 [Configuration des ImpactScopes](08_administration.md#configuration-des-impactscopes) pour notifier automatiquement des équipes transverses
- 📖 [Guide des Providers](05_notification_providers.md) pour configurer d'autres canaux (SMS, Email, Discord)
- 📖 [Webhooks Entrants](07_api_guide.md#webhooks-entrants) pour créer des incidents depuis vos outils de monitoring
