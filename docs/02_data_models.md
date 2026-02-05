# Data Models Specifications

L'application doit utiliser les modèles Django suivants. Utiliser `UUIDField` pour les clés primaires (`id`).

## 1. Organisation & Services

### Model: `Team`
Représente une équipe (ex: "SRE Core", "Backend Payment", "Legal Team").
- `id`: UUID
- `name`: CharField
- `slack_channel_id`: CharField (Canal public de l'équipe).
- `current_on_call`: ForeignKey vers User (La personne à notifier en priorité - MVP pour l'astreinte).

### Model: `Service`
Représente un actif technique (ex: "Redis Cluster", "Checkout API").
- `id`: UUID
- `name`: CharField
- `owner_team`: ForeignKey vers Team (L'équipe responsable).
- `runbook_url`: URLField (Lien vers la doc Notion/Confluence de réparation).
- `criticality`: ChoiceField (TIER_1_CRITICAL, TIER_2, TIER_3).

### Model: `ImpactScope`
Représente les impacts transverses/fonctionnels (ex: "Security Breach", "GDPR/Legal", "Public Relations").
- `id`: UUID
- `name`: CharField
- `description`: TextField
- `mandatory_notify_email`: EmailField (Optionnel: ex: dpo@company.com).
- `is_active`: Boolean

## 2. Incident Core

### Model: `Incident`
- `id`: UUID
- `title`: CharField
- `description`: TextField
- **Relations :**
    - `service`: ForeignKey vers Service (Cause technique racine, obligatoire).
    - `impacted_scopes`: ManyToManyField vers ImpactScope (Domaines touchés : Legal, Secu, etc.).
    - `lead`: ForeignKey vers User (Personne en charge de la résolution).
- **État :**
    - `severity`: ChoiceField (SEV1_CRITICAL, SEV2_HIGH, SEV3_MEDIUM, SEV4_LOW).
    - `status`: ChoiceField (TRIGGERED, ACKNOWLEDGED, MITIGATED, RESOLVED).
- **Automation Links :**
    - `lid_link`: URLField (Lien du Google Doc généré).
    - `war_room_link`: URLField (Lien du canal Slack généré).
    - `war_room_id`: CharField (ID technique pour archivage).
- **Timestamps (KPIs) :**
    - `detected_at`: DateTime (Reçu du monitoring).
    - `created_at`: DateTime (Auto add).
    - `acknowledged_at`: DateTime (Premier humain actif).
    - `resolved_at`: DateTime (Fin de l'incident).

### Model: `IncidentEvent`
Timeline de l'incident (Audit Log).
- `incident`: FK vers Incident
- `type`: ChoiceField (STATUS_CHANGE, NOTE, ALERT_SENT, DOCUMENT_CREATED, SCOPE_ADDED).
- `message`: TextField
- `timestamp`: DateTime

## 3. Configuration

### Model: `NotificationProvider`
Pour configurer les APIs sans redéployer.
- `name`: CharField (ex: "Slack Prod", "SMS Astreinte").
- `type`: ChoiceField (SLACK, DISCORD, TEAMS, OVH_SMS, SMTP, SCALEWAY_TEM, WEBHOOK, PAGERDUTY, OPSGENIE).
- `config`: JSONField (Sert à stocker Token, Webhook URL, App Key, Secret, etc.).
- `is_active`: Boolean

#### Configuration par type:

**SLACK:**
```json
{
  "bot_token": "xoxb-...",
  "default_channel": "C0123456789"
}
```

**DISCORD (Webhook mode):**
```json
{
  "webhook_url": "https://discord.com/api/webhooks/..."
}
```

**DISCORD (Bot mode):**
```json
{
  "bot_token": "your-bot-token",
  "guild_id": "server-id",
  "incidents_category_id": "category-id"
}
```

**OVH_SMS:**
```json
{
  "application_key": "app-key",
  "application_secret": "app-secret",
  "consumer_key": "consumer-key",
  "service_name": "sms-xxxxx-1",
  "sender": "IMAS"
}
```

**WEBHOOK / PAGERDUTY / OPSGENIE / TEAMS:**
```json
{
  "url": "https://webhook-endpoint/",
  "format": "json|slack|teams|pagerduty|opsgenie|custom",
  "method": "POST",
  "headers": {"Authorization": "Bearer xxx"},
  "routing_key": "for-pagerduty",
  "template": {}
}
```