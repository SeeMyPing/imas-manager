# Documentation des Providers de Notification

> Guide de configuration et d'utilisation des différents providers de notification dans IMAS Manager

---

## 📋 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Slack](#slack)
3. [Discord](#discord)
4. [Email (SMTP)](#email-smtp)
5. [OVH SMS](#ovh-sms)
6. [Webhook Générique](#webhook-générique)
7. [ntfy.sh](#ntfysh)
8. [Configuration via Admin](#configuration-via-admin)
9. [Dépannage](#dépannage)

---

## Vue d'ensemble

IMAS Manager supporte plusieurs providers de notification pour alerter les équipes lors d'incidents. Chaque provider est configuré via le modèle `NotificationProvider` dans l'administration Django.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    NotificationRouter                           │
│                                                                 │
│  Calcule les destinataires en fonction de :                     │
│  - L'équipe propriétaire du service                             │
│  - Les ImpactScopes concernés                                   │
│  - La sévérité de l'incident                                    │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    NotificationProviderFactory                   │
│                                                                 │
│  Instancie le bon provider selon le type configuré              │
└─────────────────────────────────────────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
    ┌──────────┐        ┌──────────┐        ┌──────────┐
    │  Slack   │        │  Discord │        │   SMS    │
    │ Provider │        │ Provider │        │ Provider │
    └──────────┘        └──────────┘        └──────────┘
           │                   │                   │
           ▼                   ▼                   ▼
    ┌──────────┐        ┌──────────┐        ┌──────────┐
    │ Slack API│        │Discord   │        │ OVH API  │
    │          │        │ Webhook  │        │          │
    └──────────┘        └──────────┘        └──────────┘
```

### Providers Disponibles

| Provider | Type | Cas d'Usage |
|----------|------|-------------|
| **Slack** | `SLACK` | Notifications d'équipe + War Rooms |
| **Discord** | `DISCORD` | Notifications d'équipe + War Rooms |
| **Email** | `SMTP` | Alertes officielles, stakeholders |
| **OVH SMS** | `OVH_SMS` | Alertes critiques SEV1/SEV2 |
| **Webhook** | `WEBHOOK` | Intégrations tierces (PagerDuty, Opsgenie, etc.) |
| **ntfy** | `NTFY` | Push notifications sur mobile |

---

## Slack

Le provider Slack permet d'envoyer des notifications riches via l'API Slack et de créer des War Rooms automatiquement.

### Prérequis

1. **Créer une App Slack** sur [api.slack.com/apps](https://api.slack.com/apps)
2. **Configurer les scopes OAuth** :
   - `chat:write` - Envoyer des messages
   - `channels:manage` - Créer des canaux (War Rooms)
   - `channels:read` - Lire les infos des canaux
   - `users:read` - Lire les infos utilisateurs
   - `users:read.email` - Rechercher par email

3. **Installer l'app** dans votre workspace et récupérer le `Bot User OAuth Token` (commence par `xoxb-`)

### Configuration

```json
{
  "bot_token": "xoxb-1234567890-1234567890123-abcdefghijklmnopqrstuvwx",
  "default_channel": "C0123456789"
}
```

| Clé | Requis | Description |
|-----|--------|-------------|
| `bot_token` | ✅ Oui | Token OAuth du bot Slack (xoxb-...) |
| `default_channel` | Non | ID du canal par défaut pour les notifications |

### Fonctionnalités

#### Envoi de Messages

Les messages sont formatés avec le [Block Kit](https://api.slack.com/block-kit) de Slack :

```
┌─────────────────────────────────────────────────────────────┐
│ 🔴 Redis Cluster Down - Production                         │
├─────────────────────────────────────────────────────────────┤
│ Severity: SEV1_CRITICAL    │    Service: redis-prod        │
│ Status: TRIGGERED          │                               │
├─────────────────────────────────────────────────────────────┤
│ Description:                                                │
│ All nodes reporting connection timeout. Cluster unreachable │
├─────────────────────────────────────────────────────────────┤
│ Quick Links:                                                │
│ • 📄 LID Document                                           │
│ • 📋 Runbook                                                │
│ • 💬 War Room                                               │
├─────────────────────────────────────────────────────────────┤
│ [🔍 View Incident]                                          │
└─────────────────────────────────────────────────────────────┘
```

#### Création de War Rooms

Pour les incidents SEV1/SEV2, un canal dédié est créé automatiquement :

- **Nom** : `inc-{short_id}-{service}` (ex: `inc-abc123-redis-prod`)
- **Invitations automatiques** : Lead, On-Call, équipe propriétaire
- **Message d'accueil** : Contexte de l'incident, liens utiles

#### Emojis de Sévérité

| Sévérité | Emoji |
|----------|-------|
| SEV1_CRITICAL | 🔴 |
| SEV2_HIGH | 🟠 |
| SEV3_MEDIUM | 🟡 |
| SEV4_LOW | 🟢 |

### Exemple d'Utilisation

```python
from services.notifications.providers import NotificationProviderFactory
from core.models import NotificationProvider

# Récupérer le provider configuré
config = NotificationProvider.objects.get(type="SLACK", is_active=True)
provider = NotificationProviderFactory.get_provider(config)

# Envoyer une notification
provider.send(
    recipient="C0123456789",  # Channel ID
    message={
        "title": "Redis Cluster Down",
        "body": "Connection timeout on all nodes",
        "severity": "SEV1_CRITICAL",
        "service": "redis-prod",
        "status": "TRIGGERED",
        "incident_url": "http://localhost:8000/dashboard/incidents/abc123/",
    }
)
```

---

## Discord

Le provider Discord supporte deux modes : **Webhook** (simple) et **Bot** (complet avec War Rooms).

### Mode Webhook (Simple)

Idéal pour des notifications basiques sans créer de canaux.

#### Prérequis

1. Dans Discord, aller dans **Paramètres du serveur** → **Intégrations** → **Webhooks**
2. Créer un nouveau webhook et copier l'URL

#### Configuration

```json
{
  "webhook_url": "https://discord.com/api/webhooks/1234567890/abcdefghijklmnop"
}
```

| Clé | Requis | Description |
|-----|--------|-------------|
| `webhook_url` | ✅ Oui | URL du webhook Discord |

### Mode Bot (Complet)

Permet la création de War Rooms et la gestion des permissions.

#### Prérequis

1. Créer une application sur [Discord Developer Portal](https://discord.com/developers/applications)
2. Créer un Bot et copier le token
3. Activer les **Privileged Gateway Intents** :
   - `SERVER MEMBERS INTENT`
   - `MESSAGE CONTENT INTENT`
4. Inviter le bot avec les permissions :
   - Manage Channels
   - Send Messages
   - Manage Messages
   - Embed Links
   - Mention Everyone

#### Configuration

```json
{
  "bot_token": "MTIzNDU2Nzg5MDEyMzQ1Njc4.AbCdEf.GhIjKlMnOpQrStUvWxYz",
  "guild_id": "123456789012345678",
  "incidents_category_id": "234567890123456789"
}
```

| Clé | Requis | Description |
|-----|--------|-------------|
| `bot_token` | ✅ Oui | Token du bot Discord |
| `guild_id` | ✅ Oui | ID du serveur Discord |
| `incidents_category_id` | Non | ID de la catégorie pour les War Rooms |

### Format des Messages (Embed)

```
┌─────────────────────────────────────────────────────────────┐
│ ▌                                                       [🔴] │
│ ▌ Redis Cluster Down - Production                           │
├─────────────────────────────────────────────────────────────┤
│ 🖥️ Service        ⚠️ Severity        📊 Status              │
│ redis-prod        SEV1_CRITICAL      TRIGGERED              │
├─────────────────────────────────────────────────────────────┤
│ Connection timeout on all nodes. Cluster unreachable.       │
├─────────────────────────────────────────────────────────────┤
│ 🔗 Links                                                    │
│ • Dashboard • Runbook • LID                                 │
└─────────────────────────────────────────────────────────────┘
```

### Couleurs par Sévérité

| Sévérité | Couleur | Code Hex |
|----------|---------|----------|
| SEV1_CRITICAL | Rouge | `#DC3545` |
| SEV2_HIGH | Orange | `#FD7E14` |
| SEV3_MEDIUM | Jaune | `#FFC107` |
| SEV4_LOW | Cyan | `#0DCAF0` |

---

## Email (SMTP)

Le provider Email envoie des notifications par email avec support HTML.

### Configuration Personnalisée

```json
{
  "host": "smtp.example.com",
  "port": 587,
  "username": "alerts@example.com",
  "password": "your-smtp-password",
  "use_tls": true,
  "use_ssl": false,
  "from_email": "incidents@example.com",
  "from_name": "IMAS Manager"
}
```

| Clé | Requis | Description |
|-----|--------|-------------|
| `host` | Non* | Serveur SMTP |
| `port` | Non | Port SMTP (défaut: 587) |
| `username` | Non | Identifiant SMTP |
| `password` | Non | Mot de passe SMTP |
| `use_tls` | Non | Activer TLS (défaut: true) |
| `use_ssl` | Non | Activer SSL (défaut: false) |
| `from_email` | Non | Adresse d'expéditeur |
| `from_name` | Non | Nom d'expéditeur |

> *Si non fourni, utilise les paramètres Django (`EMAIL_HOST`, `EMAIL_PORT`, etc.)

### Configuration via Django Settings

Vous pouvez également utiliser les paramètres Django par défaut :

```python
# settings.py
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.example.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'alerts@example.com'
EMAIL_HOST_PASSWORD = 'your-password'
DEFAULT_FROM_EMAIL = 'IMAS Manager <incidents@example.com>'
```

### Format du Message

**Email HTML :**

```html
<!DOCTYPE html>
<html>
<head>
  <style>
    .header { background: #dc3545; color: white; padding: 20px; }
    .content { padding: 20px; }
    .severity-badge { ... }
  </style>
</head>
<body>
  <div class="header">
    <h1>🔴 Redis Cluster Down - Production</h1>
  </div>
  <div class="content">
    <table>
      <tr><td>Severity:</td><td>SEV1_CRITICAL</td></tr>
      <tr><td>Service:</td><td>redis-prod</td></tr>
      <tr><td>Status:</td><td>TRIGGERED</td></tr>
    </table>
    <p>Connection timeout on all nodes...</p>
    <a href="...">View Incident</a>
  </div>
</body>
</html>
```

### Providers Email Populaires

#### Gmail

```json
{
  "host": "smtp.gmail.com",
  "port": 587,
  "username": "your-email@gmail.com",
  "password": "your-app-password",
  "use_tls": true
}
```

> ⚠️ Utilisez un [mot de passe d'application](https://support.google.com/accounts/answer/185833) pour Gmail.

#### Scaleway TEM

```json
{
  "host": "smtp.tem.scw.cloud",
  "port": 587,
  "username": "your-project-id",
  "password": "your-secret-key",
  "use_tls": true,
  "from_email": "incidents@your-domain.com"
}
```

#### SendGrid

```json
{
  "host": "smtp.sendgrid.net",
  "port": 587,
  "username": "apikey",
  "password": "SG.your-api-key",
  "use_tls": true
}
```

---

## OVH SMS

Le provider OVH SMS envoie des SMS via l'API OVH pour les alertes critiques (SEV1/SEV2).

### Prérequis

1. **Compte OVH** avec un service SMS actif
2. **Créer des credentials API** sur [api.ovh.com/createToken](https://api.ovh.com/createToken/)
   - Droits requis : `POST /sms/{serviceName}/jobs`

### Configuration

```json
{
  "application_key": "your-application-key",
  "application_secret": "your-application-secret",
  "consumer_key": "your-consumer-key",
  "service_name": "sms-xx12345-1",
  "sender": "IMAS"
}
```

| Clé | Requis | Description |
|-----|--------|-------------|
| `application_key` | ✅ Oui | Clé d'application OVH |
| `application_secret` | ✅ Oui | Secret d'application OVH |
| `consumer_key` | ✅ Oui | Clé consommateur OVH |
| `service_name` | ✅ Oui | Nom du service SMS (sms-xxx-1) |
| `sender` | Non | Expéditeur (défaut: numéro court) |

### Obtenir les Credentials

1. Aller sur [api.ovh.com/createToken](https://api.ovh.com/createToken/)
2. Configurer les droits :
   ```
   GET    /sms
   GET    /sms/*
   POST   /sms/*/jobs
   ```
3. Générer le token et récupérer les 3 clés

### Format du SMS

```
🔴 [IMAS] SEV1_CRITICAL
Redis Cluster Down
Service: redis-prod
https://imas.example.com/incidents/abc123
```

### Cas d'Usage

- **Alertes On-Call** : Réveiller l'astreinte pour les incidents SEV1
- **Escalade niveau 2** : Si non acquitté après X minutes
- **Notifications stakeholders** : DPO, CISO pour incidents de sécurité

---

## Webhook Générique

Le provider Webhook permet d'intégrer IMAS avec des systèmes tiers (PagerDuty, Opsgenie, etc.).

### Configuration de Base

```json
{
  "url": "https://your-endpoint.com/webhook",
  "method": "POST",
  "format": "json",
  "headers": {
    "Authorization": "Bearer your-token",
    "X-Custom-Header": "value"
  }
}
```

| Clé | Requis | Description |
|-----|--------|-------------|
| `url` | ✅ Oui | URL du webhook |
| `method` | Non | Méthode HTTP (défaut: POST) |
| `format` | Non | Format de payload (voir ci-dessous) |
| `headers` | Non | Headers HTTP personnalisés |
| `template` | Non | Template personnalisé pour format "custom" |

### Formats Supportés

#### Format JSON (défaut)

```json
{
  "source": "imas-manager",
  "event_type": "incident",
  "title": "Redis Cluster Down",
  "description": "Connection timeout on all nodes",
  "severity": "SEV1_CRITICAL",
  "status": "TRIGGERED",
  "service": "redis-prod",
  "incident_id": "abc123",
  "timestamp": "2026-02-05T18:30:00Z"
}
```

#### Format Slack (Incoming Webhook)

```json
{
  "format": "slack"
}
```

Génère un payload compatible avec les webhooks entrants Slack.

#### Format Microsoft Teams

```json
{
  "url": "https://outlook.office.com/webhook/...",
  "format": "teams"
}
```

Génère une Adaptive Card Teams :

```json
{
  "@type": "MessageCard",
  "@context": "http://schema.org/extensions",
  "themeColor": "DC3545",
  "summary": "Incident Alert",
  "sections": [
    {
      "activityTitle": "🔴 Redis Cluster Down",
      "facts": [
        {"name": "Severity", "value": "SEV1_CRITICAL"},
        {"name": "Service", "value": "redis-prod"}
      ]
    }
  ]
}
```

#### Format PagerDuty

```json
{
  "url": "https://events.pagerduty.com/v2/enqueue",
  "format": "pagerduty",
  "headers": {
    "routing_key": "your-integration-key"
  }
}
```

Payload généré :

```json
{
  "routing_key": "your-integration-key",
  "event_action": "trigger",
  "dedup_key": "imas-incident-abc123",
  "payload": {
    "summary": "Redis Cluster Down",
    "source": "imas-manager",
    "severity": "critical",
    "custom_details": {
      "service": "redis-prod",
      "status": "TRIGGERED"
    }
  }
}
```

#### Format Opsgenie

```json
{
  "url": "https://api.opsgenie.com/v2/alerts",
  "format": "opsgenie",
  "headers": {
    "Authorization": "GenieKey your-api-key"
  }
}
```

Payload généré :

```json
{
  "message": "Redis Cluster Down",
  "alias": "imas-incident-abc123",
  "description": "Connection timeout on all nodes",
  "priority": "P1",
  "source": "imas-manager",
  "tags": ["imas", "redis-prod"]
}
```

#### Format Custom (Template)

Pour un contrôle total sur le payload :

```json
{
  "url": "https://custom-system.com/api",
  "format": "custom",
  "template": {
    "alert_name": "{{title}}",
    "alert_level": "{{severity}}",
    "component": "{{service}}",
    "message": "{{body}}",
    "link": "{{incident_url}}"
  }
}
```

Variables disponibles : `{{title}}`, `{{body}}`, `{{severity}}`, `{{status}}`, `{{service}}`, `{{incident_id}}`, `{{incident_url}}`, `{{timestamp}}`

---

## ntfy.sh

[ntfy.sh](https://ntfy.sh) est un service de notifications push simple. Peut être auto-hébergé ou utiliser l'instance publique.

### Configuration

```json
{
  "server_url": "https://ntfy.sh",
  "default_topic": "imas-incidents",
  "access_token": "tk_your_access_token"
}
```

| Clé | Requis | Description |
|-----|--------|-------------|
| `server_url` | ✅ Oui | URL du serveur ntfy (ou instance auto-hébergée) |
| `default_topic` | ✅ Oui | Topic par défaut pour les notifications |
| `access_token` | Non | Token pour topics privés |
| `username` | Non | Alternative: auth basique |
| `password` | Non | Alternative: auth basique |
| `default_priority` | Non | Priorité par défaut (1-5) |
| `default_tags` | Non | Tags par défaut |

### Priorités

| Sévérité | Priorité ntfy | Description |
|----------|---------------|-------------|
| SEV1_CRITICAL | 5 (max) | Notification urgente |
| SEV2_HIGH | 4 (high) | Haute priorité |
| SEV3_MEDIUM | 3 (default) | Priorité normale |
| SEV4_LOW | 2 (low) | Basse priorité |

### Tags (Emojis)

| Sévérité | Tags |
|----------|------|
| SEV1_CRITICAL | 🚨 rotating_light, 🔥 fire, 🆘 sos |
| SEV2_HIGH | ⚠️ warning, ❗ exclamation |
| SEV3_MEDIUM | 🔔 bell, 📢 loudspeaker |
| SEV4_LOW | ℹ️ information_source |

### S'abonner aux Notifications

1. **Mobile** : Installer l'app [ntfy](https://ntfy.sh/docs/subscribe/phone/) (Android/iOS)
2. **Desktop** : Utiliser l'app web ou les notifications du navigateur
3. **CLI** : `curl -s ntfy.sh/imas-incidents/json`

### Instance Auto-hébergée

```json
{
  "server_url": "https://ntfy.your-company.com",
  "default_topic": "incidents",
  "username": "imas",
  "password": "secret"
}
```

---

## Configuration via Admin

### Accéder à l'Administration

1. Aller sur `http://localhost:8000/admin/`
2. Se connecter avec un compte superuser
3. Naviguer vers **Core** → **Notification providers**

### Créer un Provider

1. Cliquer sur **Add notification provider**
2. Remplir les champs :
   - **Name** : Nom descriptif (ex: "Slack Production")
   - **Type** : Sélectionner le type de provider
   - **Config** : Configuration JSON (voir sections ci-dessus)
   - **Is active** : Cocher pour activer

### Exemple de Configuration Multiple

```
┌─────────────────────────────────────────────────────────────────┐
│                     Notification Providers                       │
├─────────────────────────────────────────────────────────────────┤
│  ✅ Slack Production     │ SLACK    │ Canal #incidents          │
│  ✅ Discord Alerts       │ DISCORD  │ Webhook mode               │
│  ✅ Email Stakeholders   │ SMTP     │ Pour DPO, CISO            │
│  ✅ OVH SMS On-Call      │ OVH_SMS  │ Alertes SEV1 uniquement    │
│  ✅ PagerDuty            │ WEBHOOK  │ Format pagerduty           │
│  ❌ ntfy Test            │ NTFY     │ Instance de test           │
└─────────────────────────────────────────────────────────────────┘
```

### Routing des Notifications

Le `NotificationRouter` détermine quel provider utiliser selon :

1. **Sévérité** : SEV1 → SMS + Slack, SEV3 → Slack uniquement
2. **ImpactScope** : Security → Email CISO, Legal → Email DPO
3. **Équipe** : Chaque équipe peut avoir ses préférences

---

## Dépannage

### Problèmes Courants

#### Slack : "not_in_channel"

**Cause** : Le bot n'est pas dans le canal.

**Solution** : Inviter le bot dans le canal avec `/invite @IMAS-Bot`

#### Slack : "invalid_auth"

**Cause** : Token invalide ou expiré.

**Solution** : Régénérer le token dans les paramètres de l'app Slack.

#### Discord : "50001 Missing Access"

**Cause** : Le bot n'a pas les permissions nécessaires.

**Solution** : Réinviter le bot avec les bonnes permissions.

#### Email : "Connection refused"

**Cause** : Serveur SMTP inaccessible.

**Solution** : Vérifier l'host, le port et les paramètres TLS/SSL.

#### OVH SMS : "Signature mismatch"

**Cause** : Credentials incorrects ou timestamp désynchronisé.

**Solution** : Vérifier les 3 clés API et la synchronisation horaire du serveur.

### Logs de Debug

Activer les logs détaillés dans `settings.py` :

```python
LOGGING = {
    "loggers": {
        "services.notifications": {
            "level": "DEBUG",
            "handlers": ["console"],
        },
    }
}
```

### Tester un Provider

Via le shell Django :

```python
python manage.py shell

from core.models import NotificationProvider
from services.notifications.providers import NotificationProviderFactory

# Récupérer le provider
config = NotificationProvider.objects.get(name="Slack Production")
provider = NotificationProviderFactory.get_provider(config)

# Tester l'envoi
result = provider.send(
    recipient="C0123456789",
    message={
        "title": "Test Notification",
        "body": "This is a test from IMAS Manager",
        "severity": "SEV4_LOW",
        "status": "TRIGGERED",
        "service": "test-service",
    }
)

print(f"Envoi réussi: {result}")
```

---

## Résumé des Configurations

### Slack

```json
{"bot_token": "xoxb-xxx", "default_channel": "C0123456789"}
```

### Discord (Webhook)

```json
{"webhook_url": "https://discord.com/api/webhooks/xxx/yyy"}
```

### Discord (Bot)

```json
{"bot_token": "xxx", "guild_id": "123", "incidents_category_id": "456"}
```

### Email

```json
{"host": "smtp.example.com", "port": 587, "username": "x", "password": "y", "use_tls": true}
```

### OVH SMS

```json
{"application_key": "x", "application_secret": "y", "consumer_key": "z", "service_name": "sms-xxx-1"}
```

### Webhook (PagerDuty)

```json
{"url": "https://events.pagerduty.com/v2/enqueue", "format": "pagerduty", "headers": {"routing_key": "xxx"}}
```

### ntfy

```json
{"server_url": "https://ntfy.sh", "default_topic": "imas-incidents", "access_token": "tk_xxx"}
```

---

*Documentation générée le 5 février 2026 - IMAS Manager v1.0*
