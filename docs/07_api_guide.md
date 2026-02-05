# Guide de l'API

> Documentation complète de l'API REST IMAS Manager

---

## 📋 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Authentification](#authentification)
3. [Endpoints Incidents](#endpoints-incidents)
4. [Endpoints Services & Teams](#endpoints-services--teams)
5. [Endpoints Runbooks & Tags](#endpoints-runbooks--tags)
6. [Endpoints Métriques](#endpoints-métriques)
7. [Webhooks Entrants](#webhooks-entrants)
8. [Intégration Slack](#intégration-slack)
9. [Codes d'Erreur](#codes-derreur)
10. [Rate Limiting](#rate-limiting)
11. [Exemples d'Intégration](#exemples-dintégration)

---

## Vue d'ensemble

### Base URL

```
https://imas.example.com/api/v1/
```

### Format

- **Content-Type** : `application/json`
- **Encoding** : UTF-8
- **Pagination** : 20 éléments par défaut, max 100

### Documentation Interactive

- **Swagger UI** : `/api/docs/`
- **ReDoc** : `/api/redoc/`
- **OpenAPI Schema** : `/api/schema/`

---

## Authentification

### Token Authentication

IMAS Manager utilise l'authentification par token. Incluez le token dans le header `Authorization` :

```
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
```

### Obtenir un Token

```bash
POST /api/auth/token/
```

**Request :**

```json
{
  "username": "admin",
  "password": "your-password"
}
```

**Response (200 OK) :**

```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "user_id": 1,
  "username": "admin",
  "created": true
}
```

**Exemple curl :**

```bash
curl -X POST https://imas.example.com/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}'
```

### Révoquer un Token

```bash
POST /api/auth/token/revoke/
Authorization: Token <your-token>
```

**Response (200 OK) :**

```json
{
  "message": "Token revoked successfully"
}
```

### Vérifier un Token

```bash
GET /api/auth/token/verify/
Authorization: Token <your-token>
```

**Response (200 OK) :**

```json
{
  "valid": true,
  "user_id": 1,
  "username": "admin"
}
```

---

## Endpoints Incidents

### Lister les Incidents

```bash
GET /api/v1/incidents/
```

**Query Parameters :**

| Paramètre | Type | Description |
|-----------|------|-------------|
| `status` | string | `triggered`, `acknowledged`, `mitigated`, `resolved` |
| `severity` | string | `SEV1_CRITICAL`, `SEV2_HIGH`, `SEV3_MEDIUM`, `SEV4_LOW` |
| `service` | UUID | ID du service |
| `search` | string | Recherche dans titre et description |
| `ordering` | string | `-created_at`, `severity`, `status` |
| `page` | int | Numéro de page |
| `page_size` | int | Taille de page (max 100) |

**Response (200 OK) :**

```json
{
  "count": 42,
  "next": "https://imas.example.com/api/v1/incidents/?page=2",
  "previous": null,
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "short_id": "INC-A1B2C3",
      "title": "Redis Cluster Down",
      "description": "Connection timeout on all nodes",
      "severity": "SEV1_CRITICAL",
      "status": "TRIGGERED",
      "service": {
        "id": "...",
        "name": "redis-prod"
      },
      "lead": {
        "id": 1,
        "username": "admin"
      },
      "created_at": "2026-02-05T18:30:00Z",
      "acknowledged_at": null,
      "resolved_at": null
    }
  ]
}
```

**Exemple curl :**

```bash
curl -X GET "https://imas.example.com/api/v1/incidents/?status=triggered&severity=SEV1_CRITICAL" \
  -H "Authorization: Token <your-token>"
```

### Créer un Incident

```bash
POST /api/v1/incidents/
```

**Request :**

```json
{
  "title": "Redis Cluster Down",
  "description": "All nodes reporting connection timeout. Cluster unreachable.",
  "service": "550e8400-e29b-41d4-a716-446655440000",
  "severity": "SEV1_CRITICAL",
  "impacted_scopes": [
    "660e8400-e29b-41d4-a716-446655440001"
  ],
  "detected_at": "2026-02-05T18:25:00Z"
}
```

| Champ | Requis | Description |
|-------|--------|-------------|
| `title` | ✅ | Titre de l'incident (max 200 chars) |
| `description` | Non | Description détaillée |
| `service` | ✅ | UUID du service impacté |
| `severity` | Non | Défaut: `SEV3_MEDIUM` |
| `impacted_scopes` | Non | Liste d'UUIDs des ImpactScopes |
| `detected_at` | Non | Timestamp de détection (défaut: now) |

**Response (201 Created) :**

```json
{
  "id": "770e8400-e29b-41d4-a716-446655440000",
  "short_id": "INC-X1Y2Z3",
  "title": "Redis Cluster Down",
  "status": "TRIGGERED",
  "war_room_link": null,
  "lid_link": null,
  "message": "Incident created. Orchestration in progress..."
}
```

### Détail d'un Incident

```bash
GET /api/v1/incidents/{id}/
```

**Response (200 OK) :**

```json
{
  "id": "770e8400-e29b-41d4-a716-446655440000",
  "short_id": "INC-X1Y2Z3",
  "title": "Redis Cluster Down",
  "description": "All nodes reporting connection timeout.",
  "severity": "SEV1_CRITICAL",
  "severity_display": "SEV1 - Critical",
  "status": "TRIGGERED",
  "status_display": "Triggered",
  "service": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "redis-prod",
    "owner_team": {
      "id": "...",
      "name": "SRE Core"
    },
    "runbook_url": "https://wiki.example.com/redis-recovery"
  },
  "impacted_scopes": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "name": "Data Loss Risk"
    }
  ],
  "lead": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com"
  },
  "war_room_link": "https://slack.com/app_redirect?channel=C0123456789",
  "lid_link": "https://docs.google.com/document/d/xxx",
  "created_at": "2026-02-05T18:30:00Z",
  "detected_at": "2026-02-05T18:25:00Z",
  "acknowledged_at": null,
  "resolved_at": null,
  "kpis": {
    "mttd_seconds": 300,
    "mtta_seconds": null,
    "mttr_seconds": null
  },
  "timeline": [
    {
      "id": "...",
      "type": "STATUS_CHANGE",
      "message": "Incident created",
      "timestamp": "2026-02-05T18:30:00Z"
    }
  ]
}
```

### Acquitter un Incident

```bash
POST /api/v1/incidents/{id}/acknowledge/
```

**Request (optionnel) :**

```json
{
  "message": "Investigating the issue"
}
```

**Response (200 OK) :**

```json
{
  "id": "770e8400-e29b-41d4-a716-446655440000",
  "status": "ACKNOWLEDGED",
  "acknowledged_at": "2026-02-05T18:35:00Z",
  "acknowledged_by": {
    "id": 1,
    "username": "admin"
  },
  "message": "Incident acknowledged successfully"
}
```

### Résoudre un Incident

```bash
POST /api/v1/incidents/{id}/resolve/
```

**Request :**

```json
{
  "resolution_note": "Redis cluster recovered after failover.",
  "root_cause": "Memory exhaustion on primary node"
}
```

**Response (200 OK) :**

```json
{
  "id": "770e8400-e29b-41d4-a716-446655440000",
  "status": "RESOLVED",
  "resolved_at": "2026-02-05T19:00:00Z",
  "resolved_by": {
    "id": 1,
    "username": "admin"
  },
  "kpis": {
    "mttd_seconds": 300,
    "mtta_seconds": 300,
    "mttr_seconds": 1800
  }
}
```

### Commentaires d'un Incident

#### Lister les commentaires

```bash
GET /api/v1/incidents/{id}/comments/
```

#### Ajouter un commentaire

```bash
POST /api/v1/incidents/{id}/comments/
```

```json
{
  "content": "Failover completed, monitoring recovery.",
  "comment_type": "update"
}
```

### Tags d'un Incident

#### Ajouter des tags

```bash
POST /api/v1/incidents/{id}/tags/
```

```json
{
  "tags": ["postmortem-required", "customer-impact"]
}
```

---

## Endpoints Services & Teams

### Lister les Services

```bash
GET /api/v1/services/
```

**Response :**

```json
{
  "count": 15,
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "redis-prod",
      "owner_team": {
        "id": "...",
        "name": "SRE Core"
      },
      "criticality": "TIER_1_CRITICAL",
      "runbook_url": "https://wiki.example.com/redis"
    }
  ]
}
```

### Détail d'un Service

```bash
GET /api/v1/services/{id}/
```

### Lister les Teams

```bash
GET /api/v1/teams/
```

**Response :**

```json
{
  "count": 5,
  "results": [
    {
      "id": "...",
      "name": "SRE Core",
      "slack_channel_id": "C0123456789",
      "current_on_call": {
        "id": 2,
        "username": "oncall-user",
        "email": "oncall@example.com"
      }
    }
  ]
}
```

---

## Endpoints Runbooks & Tags

### Runbooks

#### Lister les Runbooks

```bash
GET /api/v1/runbooks/
```

#### Détail d'un Runbook

```bash
GET /api/v1/runbooks/{id}/
```

**Response :**

```json
{
  "id": "...",
  "title": "Redis Cluster Recovery",
  "description": "Steps to recover a failed Redis cluster",
  "service": {
    "id": "...",
    "name": "redis-prod"
  },
  "steps": [
    {
      "id": "...",
      "order": 1,
      "title": "Check cluster status",
      "description": "Verify the state of all nodes",
      "command": "redis-cli cluster info",
      "expected_duration_minutes": 2,
      "is_critical": false,
      "requires_confirmation": false
    },
    {
      "id": "...",
      "order": 2,
      "title": "Identify failed nodes",
      "command": "redis-cli cluster nodes | grep fail",
      "is_critical": true
    }
  ],
  "created_at": "2026-01-15T10:00:00Z",
  "updated_at": "2026-01-20T14:30:00Z"
}
```

### Tags

#### Lister les Tags

```bash
GET /api/v1/tags/
```

#### Créer un Tag

```bash
POST /api/v1/tags/
```

```json
{
  "name": "postmortem-required",
  "color": "#dc3545"
}
```

---

## Endpoints Métriques

### Résumé des Métriques

```bash
GET /api/v1/metrics/summary/
```

**Query Parameters :**

| Paramètre | Description | Défaut |
|-----------|-------------|--------|
| `period` | `7d`, `30d`, `90d`, `1y` | `30d` |

**Response :**

```json
{
  "period": "30d",
  "total_incidents": 42,
  "open_incidents": 3,
  "resolved_incidents": 39,
  "avg_mttd_seconds": 180,
  "avg_mtta_seconds": 420,
  "avg_mttr_seconds": 3600,
  "incidents_by_severity": {
    "SEV1_CRITICAL": 5,
    "SEV2_HIGH": 12,
    "SEV3_MEDIUM": 20,
    "SEV4_LOW": 5
  }
}
```

### Tendances

```bash
GET /api/v1/metrics/trends/
```

**Response :**

```json
{
  "period": "30d",
  "data": [
    {"date": "2026-01-06", "incidents": 3, "mttr_avg": 3200},
    {"date": "2026-01-13", "incidents": 5, "mttr_avg": 2800},
    {"date": "2026-01-20", "incidents": 2, "mttr_avg": 4100}
  ]
}
```

### Top Offenders (Services avec le plus d'incidents)

```bash
GET /api/v1/metrics/top-offenders/
```

### Métriques par Service

```bash
GET /api/v1/metrics/by-service/
```

### Export CSV

```bash
GET /api/v1/metrics/export/?format=csv
```

---

## Webhooks Entrants

Les webhooks permettent de recevoir des alertes depuis des outils de monitoring externes.

### Prometheus Alertmanager

```bash
POST /api/v1/webhooks/alertmanager/
```

**Payload :**

```json
{
  "version": "4",
  "groupKey": "{}:{alertname=\"HighLatency\"}",
  "status": "firing",
  "receiver": "imas",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "HighLatency",
        "severity": "critical",
        "service": "api-gateway",
        "namespace": "production"
      },
      "annotations": {
        "summary": "High latency on API Gateway",
        "description": "P99 latency > 500ms for 5 minutes"
      },
      "startsAt": "2026-02-05T18:00:00Z",
      "generatorURL": "http://prometheus:9090/graph"
    }
  ]
}
```

**Configuration Alertmanager :**

```yaml
receivers:
  - name: imas
    webhook_configs:
      - url: 'https://imas.example.com/api/v1/webhooks/alertmanager/'
        send_resolved: true
```

### Datadog

```bash
POST /api/v1/webhooks/datadog/
```

**Payload :**

```json
{
  "id": "1234567890",
  "title": "High CPU on web-server-01",
  "alert_status": "Triggered",
  "alert_type": "error",
  "tags": "service:web-app,env:production",
  "body": "CPU usage exceeded 90% for 10 minutes",
  "alert_metric": "system.cpu.user",
  "last_updated": "1707152400"
}
```

**Configuration Datadog :**

1. Aller dans **Integrations** → **Webhooks**
2. Créer un nouveau webhook avec l'URL : `https://imas.example.com/api/v1/webhooks/datadog/`
3. Utiliser le webhook dans un monitor

### Grafana

```bash
POST /api/v1/webhooks/grafana/
```

**Payload (Grafana Alerting) :**

```json
{
  "status": "firing",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "HighMemory",
        "service": "database"
      },
      "annotations": {
        "summary": "Memory usage high",
        "description": "Memory > 90% on database server"
      }
    }
  ]
}
```

### Webhook Générique

```bash
POST /api/v1/webhooks/generic/
```

**Payload :**

```json
{
  "title": "Custom Alert",
  "description": "Something happened",
  "severity": "high",
  "service": "my-service",
  "source": "custom-monitor",
  "labels": {
    "environment": "production"
  }
}
```

### Mapping de Sévérité

| Source | Valeur | IMAS Severity |
|--------|--------|---------------|
| Alertmanager | `critical` | SEV1_CRITICAL |
| Alertmanager | `warning` | SEV2_HIGH |
| Datadog | `error` | SEV1_CRITICAL |
| Datadog | `warning` | SEV2_HIGH |
| Grafana | `critical` | SEV1_CRITICAL |
| Generic | `critical`, `high` | SEV1_CRITICAL, SEV2_HIGH |

---

## Intégration Slack

### Events API

```bash
POST /api/v1/slack/events/
```

Point d'entrée pour les événements Slack (mentions, messages).

### Slash Commands

```bash
POST /api/v1/slack/commands/
```

**Commandes supportées :**

| Commande | Description |
|----------|-------------|
| `/imas incident list` | Lister les incidents ouverts |
| `/imas incident create` | Créer un incident (ouvre un modal) |
| `/imas incident ack <id>` | Acquitter un incident |
| `/imas incident resolve <id>` | Résoudre un incident |

### Interactive Components

```bash
POST /api/v1/slack/interactive/
```

Gère les interactions avec les boutons et modals Slack.

---

## Codes d'Erreur

### Codes HTTP

| Code | Signification |
|------|---------------|
| 200 | OK - Requête réussie |
| 201 | Created - Ressource créée |
| 204 | No Content - Succès sans contenu |
| 400 | Bad Request - Données invalides |
| 401 | Unauthorized - Token manquant ou invalide |
| 403 | Forbidden - Permissions insuffisantes |
| 404 | Not Found - Ressource non trouvée |
| 409 | Conflict - Conflit (ex: doublon) |
| 429 | Too Many Requests - Rate limit atteint |
| 500 | Internal Server Error - Erreur serveur |

### Format des Erreurs

```json
{
  "error": "Validation failed",
  "details": {
    "title": ["This field is required."],
    "service": ["Service with this ID does not exist."]
  }
}
```

### Erreurs Courantes

| Erreur | Cause | Solution |
|--------|-------|----------|
| `Invalid credentials` | Mauvais username/password | Vérifier les credentials |
| `Token expired` | Token révoqué | Regénérer le token |
| `Permission denied` | Droits insuffisants | Vérifier les permissions utilisateur |
| `Incident already exists` | Déduplication | Utiliser l'incident existant |

---

## Rate Limiting

### Limites

| Endpoint | Limite | Période |
|----------|--------|---------|
| Auth | 5 req | 1 minute |
| Webhooks | 100 req | 1 minute |
| API standard | 1000 req | 1 heure |

### Headers de Rate Limit

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 950
X-RateLimit-Reset: 1707156000
```

### Réponse 429

```json
{
  "error": "Rate limit exceeded",
  "retry_after": 3600
}
```

---

## Exemples d'Intégration

### Python (requests)

```python
import requests

BASE_URL = "https://imas.example.com/api/v1"
TOKEN = "your-api-token"

headers = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json"
}

# Créer un incident
response = requests.post(
    f"{BASE_URL}/incidents/",
    headers=headers,
    json={
        "title": "API Gateway Timeout",
        "description": "All requests timing out",
        "service": "550e8400-e29b-41d4-a716-446655440000",
        "severity": "SEV1_CRITICAL"
    }
)

incident = response.json()
print(f"Created incident: {incident['short_id']}")

# Lister les incidents ouverts
response = requests.get(
    f"{BASE_URL}/incidents/",
    headers=headers,
    params={"status": "triggered"}
)

for inc in response.json()["results"]:
    print(f"{inc['short_id']}: {inc['title']}")
```

### JavaScript (fetch)

```javascript
const BASE_URL = 'https://imas.example.com/api/v1';
const TOKEN = 'your-api-token';

const headers = {
  'Authorization': `Token ${TOKEN}`,
  'Content-Type': 'application/json'
};

// Créer un incident
async function createIncident() {
  const response = await fetch(`${BASE_URL}/incidents/`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      title: 'API Gateway Timeout',
      description: 'All requests timing out',
      service: '550e8400-e29b-41d4-a716-446655440000',
      severity: 'SEV1_CRITICAL'
    })
  });
  
  const incident = await response.json();
  console.log(`Created incident: ${incident.short_id}`);
}
```

### cURL

```bash
# Créer un incident
curl -X POST https://imas.example.com/api/v1/incidents/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Database Connection Pool Exhausted",
    "description": "No available connections in pool",
    "service": "550e8400-e29b-41d4-a716-446655440000",
    "severity": "SEV2_HIGH"
  }'

# Acquitter un incident
curl -X POST https://imas.example.com/api/v1/incidents/INC-ABC123/acknowledge/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Investigating"}'

# Résoudre un incident
curl -X POST https://imas.example.com/api/v1/incidents/INC-ABC123/resolve/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "resolution_note": "Increased pool size, monitoring",
    "root_cause": "Unexpected traffic spike"
  }'
```

---

*Documentation générée le 5 février 2026 - IMAS Manager v1.0*
