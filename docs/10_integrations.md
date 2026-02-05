# Guide d'Intégration

> Intégrer IMAS Manager avec vos outils de monitoring et collaboration

---

## 📋 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Prometheus / Alertmanager](#prometheus--alertmanager)
3. [Datadog](#datadog)
4. [Grafana](#grafana)
5. [Sentry](#sentry)
6. [Google Drive (LID)](#google-drive-lid)
7. [Slack](#slack)
8. [Discord](#discord)
9. [Single Sign-On (SSO)](#single-sign-on-sso)
10. [Webhooks Sortants](#webhooks-sortants)

---

## Vue d'ensemble

IMAS Manager peut s'intégrer avec de nombreux outils :

```
┌─────────────────────────────────────────────────────────────────┐
│                     Sources d'Alertes                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │Prometheus│ │ Datadog  │ │ Grafana  │ │  Sentry  │            │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘            │
│       │            │            │            │                   │
│       └────────────┴─────┬──────┴────────────┘                   │
│                          ▼                                       │
│              ┌───────────────────────┐                           │
│              │    IMAS Manager       │                           │
│              │                       │                           │
│              │  Webhooks Entrants    │                           │
│              └───────────────────────┘                           │
│                          │                                       │
│       ┌──────────────────┼──────────────────┐                   │
│       ▼                  ▼                  ▼                   │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐              │
│  │  Slack   │      │ Discord  │      │ Google   │              │
│  │          │      │          │      │ Drive    │              │
│  └──────────┘      └──────────┘      └──────────┘              │
│                     Notifications & Documentation                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prometheus / Alertmanager

### Configuration Alertmanager

Ajoutez IMAS comme receiver dans votre `alertmanager.yml` :

```yaml
# alertmanager.yml

global:
  resolve_timeout: 5m

route:
  receiver: 'default'
  group_by: ['alertname', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  
  routes:
    # Alertes critiques → IMAS
    - receiver: 'imas-critical'
      match:
        severity: critical
      continue: true
    
    # Alertes warning → IMAS
    - receiver: 'imas-warning'
      match:
        severity: warning

receivers:
  - name: 'default'
    # Votre receiver par défaut
    
  - name: 'imas-critical'
    webhook_configs:
      - url: 'https://imas.example.com/api/v1/webhooks/alertmanager/'
        send_resolved: true
        http_config:
          # Optionnel: authentification
          # bearer_token: 'your-webhook-secret'

  - name: 'imas-warning'
    webhook_configs:
      - url: 'https://imas.example.com/api/v1/webhooks/alertmanager/'
        send_resolved: true
```

### Labels Recommandés

Pour un mapping automatique vers IMAS, incluez ces labels dans vos règles Prometheus :

```yaml
# prometheus/rules/alerts.yml

groups:
  - name: infrastructure
    rules:
      - alert: RedisDown
        expr: redis_up == 0
        for: 1m
        labels:
          severity: critical        # → SEV1_CRITICAL
          service: redis-prod       # → Mappé au Service IMAS
          team: sre                 # → Optionnel
        annotations:
          summary: "Redis cluster is down"
          description: "Redis instance {{ $labels.instance }} is unreachable"
          runbook_url: "https://wiki.example.com/redis-recovery"

      - alert: HighMemoryUsage
        expr: node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes < 0.1
        for: 5m
        labels:
          severity: warning         # → SEV2_HIGH
          service: kubernetes       # → Service IMAS
        annotations:
          summary: "High memory usage on {{ $labels.instance }}"
```

### Mapping de Sévérité

| Label Prometheus | IMAS Severity |
|------------------|---------------|
| `critical` | SEV1_CRITICAL |
| `warning` | SEV2_HIGH |
| `info` | SEV3_MEDIUM |
| (non défini) | SEV3_MEDIUM |

### Résolution Automatique

Quand Alertmanager envoie un `status: resolved`, IMAS peut automatiquement :
- Ajouter un commentaire "Alert resolved by monitoring"
- Optionnellement fermer l'incident (configurable)

---

## Datadog

### Configuration du Webhook

1. **Datadog** → **Integrations** → **Webhooks**
2. Créer un nouveau webhook :

| Champ | Valeur |
|-------|--------|
| Name | `IMAS Manager` |
| URL | `https://imas.example.com/api/v1/webhooks/datadog/` |
| Custom Headers | `Content-Type: application/json` |

3. Payload personnalisé (optionnel) :

```json
{
  "id": "$ID",
  "title": "$EVENT_TITLE",
  "alert_status": "$ALERT_STATUS",
  "alert_type": "$ALERT_TYPE",
  "tags": "$TAGS",
  "body": "$EVENT_MSG",
  "alert_metric": "$ALERT_METRIC",
  "last_updated": "$LAST_UPDATED",
  "priority": "$PRIORITY",
  "hostname": "$HOSTNAME",
  "link": "$LINK"
}
```

### Utilisation dans les Monitors

Dans vos monitors Datadog, utilisez le webhook :

```
{{#is_alert}}
@webhook-IMAS-Manager
{{/is_alert}}

{{#is_recovery}}
@webhook-IMAS-Manager
{{/is_recovery}}
```

### Tags pour le Mapping

Utilisez des tags pour mapper automatiquement vers les services IMAS :

```
service:redis-prod
env:production
team:sre
```

### Mapping de Sévérité

| Datadog Alert Type | IMAS Severity |
|--------------------|---------------|
| `error` | SEV1_CRITICAL |
| `warning` | SEV2_HIGH |
| `info` | SEV3_MEDIUM |
| `success` | (résolution) |

---

## Grafana

### Configuration du Contact Point

1. **Grafana** → **Alerting** → **Contact points** → **Add contact point**

| Champ | Valeur |
|-------|--------|
| Name | `IMAS Manager` |
| Type | `Webhook` |
| URL | `https://imas.example.com/api/v1/webhooks/grafana/` |
| HTTP Method | `POST` |

2. Optionnellement, ajouter des headers :

```
Authorization: Bearer your-webhook-secret
```

### Configuration des Notification Policies

1. **Alerting** → **Notification policies** → **Edit default policy**
2. Ajouter IMAS comme contact point

### Labels pour le Routing

Dans vos alertes Grafana, utilisez des labels :

```yaml
labels:
  severity: critical
  service: api-gateway
  team: backend
```

---

## Sentry

### Webhook via Integrations

1. **Sentry** → **Settings** → **Integrations** → **Webhooks**
2. Ajouter l'URL : `https://imas.example.com/api/v1/webhooks/generic/`

### Configuration des Alertes

1. **Alerts** → **Create Alert Rule**
2. Conditions : Error count, New issues, etc.
3. Action : Send notification via Webhook

### Payload Sentry

Sentry envoie un payload qui sera parsé par IMAS :

```json
{
  "action": "triggered",
  "data": {
    "issue": {
      "id": "12345",
      "title": "TypeError: Cannot read property 'foo' of undefined",
      "culprit": "src/api/handler.js",
      "level": "error",
      "project": {
        "slug": "my-app"
      }
    }
  }
}
```

### Mapping vers IMAS

Configurez une règle d'alerte dans IMAS pour mapper les projets Sentry vers des services :

| Sentry Project | IMAS Service |
|----------------|--------------|
| `my-app` | `frontend-app` |
| `api-backend` | `api-gateway` |

---

## Google Drive (LID)

Le LID (Lead Incident Document) est automatiquement créé pour documenter l'incident.

### Configuration du Service Account

1. **Google Cloud Console** → **IAM & Admin** → **Service Accounts**
2. Créer un service account : `imas-lid-creator`
3. Télécharger le fichier JSON de credentials

### Permissions

Donnez au service account les permissions :

- **Google Drive API** : Créer des fichiers
- **Accès au dossier** : Editeur sur le dossier de destination

### Configuration IMAS

Ajoutez les credentials dans les variables d'environnement :

```bash
# .env
GOOGLE_DRIVE_CREDENTIALS_PATH=/path/to/service-account.json
GOOGLE_DRIVE_TEMPLATE_ID=1abc...xyz
GOOGLE_DRIVE_FOLDER_ID=1folder...id
```

Ou en base64 :

```bash
GOOGLE_DRIVE_CREDENTIALS_BASE64=$(base64 < service-account.json)
```

### Template du LID

Créez un template Google Doc avec les placeholders :

```
# Incident Report - {{INCIDENT_ID}}

## Résumé
- **Titre**: {{TITLE}}
- **Sévérité**: {{SEVERITY}}
- **Service**: {{SERVICE}}
- **Statut**: {{STATUS}}

## Timeline
{{TIMELINE}}

## Impact
{{IMPACT_SCOPES}}

## Cause Racine
[À compléter]

## Actions Correctives
[À compléter]

## Leçons Apprises
[À compléter]
```

---

## Slack

### Création de l'App Slack

1. **api.slack.com** → **Your Apps** → **Create New App**
2. Choisir "From scratch"
3. Nom : `IMAS Manager`
4. Workspace : Sélectionner votre workspace

### OAuth Scopes

Ajouter ces scopes dans **OAuth & Permissions** :

```
# Bot Token Scopes
channels:manage         # Créer des War Rooms
channels:read           # Lire les infos des canaux
chat:write             # Envoyer des messages
users:read             # Lire les infos utilisateurs
users:read.email       # Rechercher par email
groups:write           # Créer des canaux privés (optionnel)
```

### Event Subscriptions

1. Activer **Event Subscriptions**
2. Request URL : `https://imas.example.com/api/v1/slack/events/`
3. Subscribe to bot events :
   - `app_mention`
   - `message.channels` (optionnel)

### Slash Commands

Créer des commandes dans **Slash Commands** :

| Commande | Request URL | Description |
|----------|-------------|-------------|
| `/imas` | `https://imas.example.com/api/v1/slack/commands/` | Commandes IMAS |

### Interactivity

1. Activer **Interactivity & Shortcuts**
2. Request URL : `https://imas.example.com/api/v1/slack/interactive/`

### Installation

1. **Install to Workspace**
2. Copier le **Bot User OAuth Token** (xoxb-...)
3. Configurer dans IMAS :

```json
{
  "bot_token": "xoxb-your-token-here",
  "default_channel": "C0123456789"
}
```

### Commandes Disponibles

```
/imas help                    # Aide
/imas incident list           # Lister les incidents ouverts
/imas incident create         # Créer un incident
/imas incident ack <id>       # Acquitter
/imas incident resolve <id>   # Résoudre
/imas oncall                  # Voir qui est d'astreinte
```

---

## Discord

### Mode Webhook (Simple)

1. **Discord** → **Server Settings** → **Integrations** → **Webhooks**
2. Créer un webhook
3. Copier l'URL

Configuration IMAS :

```json
{
  "webhook_url": "https://discord.com/api/webhooks/..."
}
```

### Mode Bot (Complet)

1. **Discord Developer Portal** → **Applications** → **New Application**
2. **Bot** → **Add Bot**
3. Copier le token

Permissions requises :
- Manage Channels
- Send Messages
- Embed Links
- Mention Everyone

URL d'invitation :

```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=268437520&scope=bot
```

Configuration IMAS :

```json
{
  "bot_token": "your-bot-token",
  "guild_id": "your-server-id",
  "incidents_category_id": "category-for-war-rooms"
}
```

---

## Single Sign-On (SSO)

### SAML 2.0

IMAS supporte l'authentification SAML via `django-saml2-auth`.

#### Configuration

```python
# settings.py

SAML2_AUTH = {
    'METADATA_AUTO_CONF_URL': 'https://idp.example.com/metadata',
    'ENTITY_ID': 'https://imas.example.com/saml2/metadata/',
    'ASSERTION_URL': 'https://imas.example.com/saml2/acs/',
    'DEFAULT_NEXT_URL': '/dashboard/',
    'CREATE_USER': True,
    'NEW_USER_PROFILE': {
        'USER_GROUPS': ['Responders'],
        'ACTIVE_STATUS': True,
        'STAFF_STATUS': False,
    },
    'ATTRIBUTES_MAP': {
        'email': 'mail',
        'username': 'uid',
        'first_name': 'givenName',
        'last_name': 'sn',
    },
}
```

#### Okta

1. **Okta Admin** → **Applications** → **Create App Integration**
2. Type : SAML 2.0
3. Configuration :

| Champ | Valeur |
|-------|--------|
| Single Sign On URL | `https://imas.example.com/saml2/acs/` |
| Audience URI | `https://imas.example.com/saml2/metadata/` |

### OpenID Connect (OIDC)

Via `mozilla-django-oidc` :

```python
# settings.py

OIDC_RP_CLIENT_ID = 'your-client-id'
OIDC_RP_CLIENT_SECRET = 'your-client-secret'
OIDC_OP_AUTHORIZATION_ENDPOINT = 'https://idp.example.com/auth'
OIDC_OP_TOKEN_ENDPOINT = 'https://idp.example.com/token'
OIDC_OP_USER_ENDPOINT = 'https://idp.example.com/userinfo'
OIDC_OP_JWKS_ENDPOINT = 'https://idp.example.com/.well-known/jwks.json'

AUTHENTICATION_BACKENDS = [
    'mozilla_django_oidc.auth.OIDCAuthenticationBackend',
    'django.contrib.auth.backends.ModelBackend',
]
```

### Azure AD

```python
# Configuration Azure AD OIDC
OIDC_RP_CLIENT_ID = 'your-azure-app-id'
OIDC_RP_CLIENT_SECRET = 'your-azure-secret'
OIDC_OP_AUTHORIZATION_ENDPOINT = 'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize'
OIDC_OP_TOKEN_ENDPOINT = 'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token'
OIDC_OP_USER_ENDPOINT = 'https://graph.microsoft.com/oidc/userinfo'
```

---

## Webhooks Sortants

IMAS peut envoyer des webhooks vers des systèmes externes lors d'événements.

### Configuration

1. **Admin** → **Core** → **Notification Providers** → **Add**
2. Type : `WEBHOOK`

### Événements Supportés

| Événement | Description |
|-----------|-------------|
| `incident.created` | Nouvel incident créé |
| `incident.acknowledged` | Incident acquitté |
| `incident.resolved` | Incident résolu |
| `incident.escalated` | Escalade déclenchée |
| `comment.added` | Commentaire ajouté |

### Payload d'Exemple

```json
{
  "event": "incident.created",
  "timestamp": "2026-02-05T18:30:00Z",
  "data": {
    "incident": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "short_id": "INC-ABC123",
      "title": "Redis Cluster Down",
      "severity": "SEV1_CRITICAL",
      "status": "TRIGGERED",
      "service": {
        "id": "...",
        "name": "redis-prod"
      },
      "url": "https://imas.example.com/dashboard/incidents/INC-ABC123/"
    }
  }
}
```

### Intégration avec des Outils Tiers

#### Jira (Création automatique de tickets)

```json
{
  "url": "https://your-domain.atlassian.net/rest/api/3/issue",
  "format": "custom",
  "headers": {
    "Authorization": "Basic base64(email:api-token)",
    "Content-Type": "application/json"
  },
  "template": {
    "fields": {
      "project": {"key": "INC"},
      "summary": "{{title}}",
      "description": "{{body}}",
      "issuetype": {"name": "Incident"},
      "priority": {"name": "{{severity}}"}
    }
  }
}
```

#### Microsoft Teams

```json
{
  "url": "https://outlook.office.com/webhook/...",
  "format": "teams"
}
```

#### ServiceNow

```json
{
  "url": "https://instance.service-now.com/api/now/table/incident",
  "headers": {
    "Authorization": "Basic xxx",
    "Content-Type": "application/json"
  },
  "template": {
    "short_description": "{{title}}",
    "description": "{{body}}",
    "urgency": "1",
    "impact": "1"
  }
}
```

---

*Documentation générée le 5 février 2026 - IMAS Manager v1.0*
