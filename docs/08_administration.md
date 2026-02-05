# Guide d'Administration

> Manuel d'administration pour configurer et maintenir IMAS Manager

---

## 📋 Table des Matières

1. [Accès à l'Administration](#accès-à-ladministration)
2. [Gestion des Utilisateurs](#gestion-des-utilisateurs)
3. [Configuration des Teams](#configuration-des-teams)
4. [Configuration des Services](#configuration-des-services)
5. [Configuration des ImpactScopes](#configuration-des-impactscopes)
6. [Gestion des Astreintes (On-Call)](#gestion-des-astreintes-on-call)
7. [Providers de Notification](#providers-de-notification)
8. [Sources d'Alertes](#sources-dalertes)
9. [Maintenance & Backups](#maintenance--backups)
10. [Monitoring du Système](#monitoring-du-système)

---

## Accès à l'Administration

### Interface Admin Django

Accédez à l'interface d'administration :

```
https://imas.example.com/admin/
```

### Créer un Superutilisateur

```bash
# Docker
docker exec -it imas_web python manage.py createsuperuser

# Local
python manage.py createsuperuser
```

### Sections de l'Admin

| Section | Description |
|---------|-------------|
| **Auth** | Utilisateurs et groupes Django |
| **Core** | Teams, Services, Incidents, Providers |
| **Authtoken** | Tokens API |

---

## Gestion des Utilisateurs

### Rôles et Permissions

IMAS Manager utilise un système de permissions basé sur les groupes Django :

| Groupe | Permissions |
|--------|-------------|
| **Viewers** | Lecture seule des incidents |
| **Responders** | Acquitter et commenter les incidents |
| **Operators** | Créer, modifier, résoudre les incidents |
| **Admins** | Accès complet + configuration |

### Créer un Groupe

1. **Admin** → **Auth** → **Groups** → **Add Group**
2. Nom : `Responders`
3. Sélectionner les permissions :
   - `core | incident | Can view incident`
   - `core | incident | Can acknowledge incident`
   - `core | incidentcomment | Can add incident comment`

### Ajouter un Utilisateur

1. **Admin** → **Auth** → **Users** → **Add User**
2. Remplir : Username, Password
3. Dans la section **Permissions** :
   - Cocher `Staff status` pour accès admin
   - Assigner aux groupes appropriés

### Permissions par Modèle

```
Incident:
  - view_incident    : Voir les incidents
  - add_incident     : Créer un incident
  - change_incident  : Modifier un incident
  - delete_incident  : Supprimer un incident
  - acknowledge_incident : Acquitter
  - resolve_incident : Résoudre

Team:
  - view_team, add_team, change_team, delete_team

Service:
  - view_service, add_service, change_service, delete_service
```

### Tokens API

Chaque utilisateur peut avoir un token API :

1. **Admin** → **Authtoken** → **Tokens**
2. **Add Token** → Sélectionner l'utilisateur
3. Le token est généré automatiquement

Ou via la ligne de commande :

```bash
docker exec -it imas_web python manage.py drf_create_token username
```

---

## Configuration des Teams

### Qu'est-ce qu'une Team ?

Une Team représente une équipe technique responsable d'un ou plusieurs services.

### Créer une Team

1. **Admin** → **Core** → **Teams** → **Add Team**

| Champ | Description | Exemple |
|-------|-------------|---------|
| Name | Nom de l'équipe | `SRE Core` |
| Slack Channel ID | ID du canal Slack public | `C0123456789` |
| Current On-Call | Personne d'astreinte actuelle | (sélectionner un utilisateur) |

### Exemple de Structure

```
┌─────────────────────────────────────────────────────────────┐
│                        Organisation                          │
├─────────────────────────────────────────────────────────────┤
│  Team: SRE Core                                              │
│  ├── Slack: #sre-core                                        │
│  ├── On-Call: john.doe                                       │
│  └── Services: redis-prod, postgres-prod, k8s-cluster       │
│                                                              │
│  Team: Backend Payment                                       │
│  ├── Slack: #backend-payment                                 │
│  ├── On-Call: jane.smith                                     │
│  └── Services: payment-api, checkout-service                │
│                                                              │
│  Team: Security                                              │
│  ├── Slack: #security                                        │
│  ├── On-Call: security-oncall                                │
│  └── Services: auth-service, vault                          │
└─────────────────────────────────────────────────────────────┘
```

### Bonnes Pratiques

- ✅ Chaque team devrait avoir un canal Slack dédié
- ✅ Toujours définir un On-Call (même par défaut)
- ✅ Limiter le nombre de services par team (5-10 max)
- ❌ Éviter les teams "fourre-tout"

---

## Configuration des Services

### Qu'est-ce qu'un Service ?

Un Service représente un composant technique (API, base de données, cache, etc.).

### Créer un Service

1. **Admin** → **Core** → **Services** → **Add Service**

| Champ | Description | Exemple |
|-------|-------------|---------|
| Name | Nom technique (utilisé dans les alertes) | `redis-prod` |
| Owner Team | Équipe responsable | SRE Core |
| Criticality | Niveau de criticité | `TIER_1_CRITICAL` |
| Runbook URL | Lien vers la documentation | `https://wiki.example.com/redis` |

### Niveaux de Criticité

| Tier | Description | SLA Réponse |
|------|-------------|-------------|
| `TIER_1_CRITICAL` | Critique pour le business | < 5 min |
| `TIER_2` | Important mais pas critique | < 30 min |
| `TIER_3` | Faible impact | < 4 heures |

### Mapping Service ↔ Alertes

Les alertes entrantes utilisent le nom du service pour le routing :

```yaml
# Prometheus Alert
- alert: RedisDown
  labels:
    service: redis-prod  # ← Doit correspondre au nom dans IMAS
```

### Service Inconnu

Si une alerte arrive avec un service non configuré :
- Un incident est créé avec le service "Unknown/Triage"
- L'admin devrait créer le service manquant

---

## Configuration des ImpactScopes

### Qu'est-ce qu'un ImpactScope ?

Un ImpactScope représente un domaine d'impact transverse (sécurité, légal, PR, etc.).

### Créer un ImpactScope

1. **Admin** → **Core** → **Impact Scopes** → **Add Impact Scope**

| Champ | Description | Exemple |
|-------|-------------|---------|
| Name | Nom du scope | `Security Breach` |
| Description | Description détaillée | `Compromission de données ou accès non autorisé` |
| Mandatory Notify Email | Email à notifier automatiquement | `security@example.com` |
| Is Active | Actif/Inactif | ✅ |

### Exemples d'ImpactScopes

```
┌─────────────────────────────────────────────────────────────┐
│  ImpactScope: Security Breach                                │
│  ├── Description: Compromission de données                   │
│  ├── Notify: security@example.com, ciso@example.com         │
│  └── Actions: Notification immédiate CISO                   │
├─────────────────────────────────────────────────────────────┤
│  ImpactScope: GDPR/Legal                                     │
│  ├── Description: Impact sur les données personnelles        │
│  ├── Notify: dpo@example.com, legal@example.com             │
│  └── Actions: Documentation obligatoire sous 72h            │
├─────────────────────────────────────────────────────────────┤
│  ImpactScope: Public Relations                               │
│  ├── Description: Impact visible par les clients             │
│  ├── Notify: pr@example.com, support@example.com            │
│  └── Actions: Préparation communication client              │
├─────────────────────────────────────────────────────────────┤
│  ImpactScope: Financial Impact                               │
│  ├── Description: Perte financière directe                   │
│  ├── Notify: finance@example.com, cfo@example.com           │
│  └── Actions: Estimation de l'impact                        │
└─────────────────────────────────────────────────────────────┘
```

### Utilisation

Lors de la création d'un incident, sélectionnez les ImpactScopes concernés. Les notifications seront automatiquement envoyées aux emails configurés.

---

## Gestion des Astreintes (On-Call)

### Configuration Simple

La méthode la plus simple est d'assigner directement le `current_on_call` sur chaque Team :

1. **Admin** → **Core** → **Teams**
2. Modifier la team
3. Changer le champ **Current On-Call**

### Rotation Manuelle

Pour une rotation manuelle hebdomadaire :

```bash
# Script à exécuter chaque semaine
docker exec -it imas_web python manage.py shell

from core.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()
team = Team.objects.get(name="SRE Core")
team.current_on_call = User.objects.get(username="next_oncall_user")
team.save()
```

### OnCallSchedule (Avancé)

Pour une gestion automatique des rotations :

1. **Admin** → **Core** → **On Call Schedules** → **Add**

| Champ | Description |
|-------|-------------|
| Team | Équipe concernée |
| User | Utilisateur d'astreinte |
| Start Time | Début de l'astreinte |
| End Time | Fin de l'astreinte |
| Is Primary | Astreinte principale |

### Intégration PagerDuty/Opsgenie

Pour une gestion avancée des astreintes, intégrez avec PagerDuty ou Opsgenie via les webhooks.

---

## Providers de Notification

### Vue d'ensemble

Les providers de notification déterminent comment les alertes sont envoyées.

Voir [05_notification_providers.md](05_notification_providers.md) pour la documentation complète.

### Configuration Rapide

1. **Admin** → **Core** → **Notification Providers** → **Add**

| Champ | Description |
|-------|-------------|
| Name | Nom descriptif (ex: "Slack Production") |
| Type | SLACK, DISCORD, SMTP, OVH_SMS, WEBHOOK, NTFY |
| Config | Configuration JSON spécifique au type |
| Is Active | Activer/Désactiver |

### Exemple : Slack

```json
{
  "bot_token": "xoxb-1234567890-abcdefghijklmnop",
  "default_channel": "C0123456789"
}
```

### Exemple : Email

```json
{
  "host": "smtp.gmail.com",
  "port": 587,
  "username": "alerts@company.com",
  "password": "app-password",
  "use_tls": true
}
```

---

## Sources d'Alertes

### Configuration des Sources

Les sources d'alertes définissent d'où proviennent les incidents automatiques.

1. **Admin** → **Core** → **Alert Sources** → **Add**

| Champ | Description |
|-------|-------------|
| Name | Nom de la source (Datadog, Prometheus, etc.) |
| Type | ALERTMANAGER, DATADOG, GRAFANA, CUSTOM |
| Is Active | Activer/Désactiver |
| Default Severity | Sévérité par défaut si non spécifiée |
| Config | Configuration spécifique |

### Règles d'Alertes

Les règles permettent de mapper les alertes entrantes vers les services :

1. **Admin** → **Core** → **Alert Rules** → **Add**

| Champ | Description |
|-------|-------------|
| Source | Source d'alerte |
| Match Labels | Labels à matcher (JSON) |
| Target Service | Service cible |
| Override Severity | Surcharger la sévérité |

**Exemple de Match Labels :**

```json
{
  "alertname": "HighMemory",
  "namespace": "production"
}
```

---

## Maintenance & Backups

### Sauvegarde de la Base de Données

#### Docker

```bash
# Backup
docker exec imas_postgres pg_dump -U imas_user imas_db > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20260205.sql | docker exec -i imas_postgres psql -U imas_user imas_db
```

#### Kubernetes

```bash
# Backup
kubectl exec -n imas postgres-0 -- pg_dump -U imas imas > backup.sql

# Avec CronJob
apiVersion: batch/v1
kind: CronJob
metadata:
  name: db-backup
spec:
  schedule: "0 2 * * *"  # Tous les jours à 2h
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: postgres:16
            command: ["/bin/sh", "-c"]
            args:
              - pg_dump -h postgres -U imas imas | gzip > /backups/backup-$(date +%Y%m%d).sql.gz
```

### Nettoyage des Anciennes Données

#### Archiver les Incidents Résolus

```bash
docker exec -it imas_web python manage.py shell

from datetime import timedelta
from django.utils import timezone
from core.models import Incident

# Archiver les incidents résolus depuis plus de 90 jours
old_incidents = Incident.objects.filter(
    status='RESOLVED',
    resolved_at__lt=timezone.now() - timedelta(days=90)
)

for incident in old_incidents:
    incident.is_archived = True
    incident.save()
```

#### Nettoyer les Logs d'Audit

```bash
# Supprimer les logs de plus de 1 an
from core.models import AuditLog
from datetime import timedelta
from django.utils import timezone

AuditLog.objects.filter(
    timestamp__lt=timezone.now() - timedelta(days=365)
).delete()
```

### Tâches Planifiées (Celery Beat)

Les tâches suivantes s'exécutent automatiquement :

| Tâche | Fréquence | Description |
|-------|-----------|-------------|
| `check-pending-escalations` | 5 min | Vérifier les escalades |
| `send-unacknowledged-reminders` | 15 min | Rappels incidents non acquittés |
| `auto-archive-old-incidents` | Quotidien 2h | Archiver anciens incidents |
| `daily-incident-summary` | Quotidien 8h | Rapport quotidien |
| `cleanup-stale-war-rooms` | Quotidien 3h | Nettoyer War Rooms |

### Mises à Jour

```bash
# Arrêter les services
docker compose down

# Pull les nouvelles images
docker compose pull

# Redémarrer
docker compose up -d

# Appliquer les migrations
docker exec -it imas_web python manage.py migrate
```

---

## Monitoring du Système

### Health Check

```bash
curl https://imas.example.com/api/health/
```

**Réponse attendue :**

```json
{
  "status": "healthy",
  "service": "imas-manager",
  "version": "1.0.0"
}
```

### Vérifier les Services

```bash
# Docker
docker ps
docker compose logs -f

# Vérifier Celery Worker
docker logs imas_worker | tail -20

# Vérifier Celery Beat
docker logs imas_beat | tail -20
```

### Métriques à Surveiller

| Métrique | Seuil Alerte | Description |
|----------|--------------|-------------|
| Response Time P99 | > 1s | Latence API |
| Error Rate | > 1% | Taux d'erreur HTTP |
| Queue Depth | > 100 | Tâches en attente Celery |
| DB Connections | > 80% | Pool de connexions |
| Memory Usage | > 80% | Mémoire conteneurs |

### Logs

Les logs sont disponibles dans stdout des conteneurs :

```bash
# Tous les logs
docker compose logs -f

# Logs d'un service spécifique
docker compose logs -f web

# Avec timestamp
docker compose logs -f --timestamps
```

### Alertes Système

Configurer des alertes Prometheus pour IMAS :

```yaml
groups:
- name: imas
  rules:
  - alert: IMASWebDown
    expr: up{job="imas-web"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "IMAS Web is down"

  - alert: IMASWorkerDown
    expr: up{job="imas-worker"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "IMAS Celery Worker is down"

  - alert: IMASHighLatency
    expr: histogram_quantile(0.99, http_request_duration_seconds_bucket{job="imas-web"}) > 1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "IMAS high latency detected"
```

---

*Documentation générée le 5 février 2026 - IMAS Manager v1.0*
