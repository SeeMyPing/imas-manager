# IMAS Manager - Documentation Générale

> **Incident Management At Scale** - Plateforme d'Orchestration de Réponse aux Incidents

---

## 📋 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture du Système](#architecture-du-système)
3. [Cycle de Vie d'un Incident](#cycle-de-vie-dun-incident)
4. [Workflow de Gestion des Incidents](#workflow-de-gestion-des-incidents)
5. [Composants Principaux](#composants-principaux)
6. [Fonctionnalités Clés](#fonctionnalités-clés)
7. [Déploiement](#déploiement)
8. [API Reference](#api-reference)
9. [Configuration](#configuration)
10. [Bonnes Pratiques](#bonnes-pratiques)

---

## Vue d'ensemble

### Qu'est-ce qu'IMAS Manager ?

IMAS Manager est une plateforme d'orchestration de réponse aux incidents techniques majeurs. Contrairement aux outils de monitoring classiques qui se contentent de logger des erreurs, IMAS Manager **orchestre la réponse complète** à un incident :

- **Détection** : Ingestion d'alertes provenant de multiples sources (Datadog, Prometheus, Sentry, etc.)
- **Notification** : Alertes ciblées aux bonnes équipes via les bons canaux (Slack, SMS, Email)
- **Collaboration** : Création automatique de War Rooms pour la coordination d'équipe
- **Documentation** : Génération automatique du Lead Incident Document (LID/Post-Mortem)
- **Résolution** : Runbooks guidés et procédures de réparation
- **Analyse** : KPIs et métriques pour l'amélioration continue

### Pourquoi IMAS Manager ?

| Problème | Solution IMAS |
|----------|---------------|
| Alertes multiples pour un même problème | Déduplication intelligente par fingerprint |
| "Qui appeler à 3h du matin ?" | Routing automatique vers l'astreinte (On-Call) |
| Documentation post-incident oubliée | LID généré automatiquement dès le début |
| Communication chaotique | War Room dédiée avec contexte pré-rempli |
| Procédures de réparation introuvables | Runbooks liés automatiquement au service impacté |
| Pas de visibilité sur les temps de réponse | Calcul automatique MTTD, MTTA, MTTR |

---

## Architecture du Système

### Stack Technique

```
┌─────────────────────────────────────────────────────────────────┐
│                        IMAS Manager                             │
├─────────────────────────────────────────────────────────────────┤
│  Frontend Layer                                                 │
│  ├── Django Dashboard (Templates + Tailwind CSS)                │
│  └── Django REST Framework (API v1)                             │
├─────────────────────────────────────────────────────────────────┤
│  Service Layer                                                  │
│  ├── IncidentOrchestrator    (Workflow principal)               │
│  ├── NotificationRouter      (Routage des alertes)              │
│  ├── EscalationService       (Escalade automatique)             │
│  ├── RunbookService          (Procédures guidées)               │
│  └── ChatOpsService          (Slack/Discord)                    │
├─────────────────────────────────────────────────────────────────┤
│  Async Layer (Celery + Redis)                                   │
│  ├── orchestrate_incident_task                                  │
│  ├── send_notification_task                                     │
│  ├── check_pending_escalations                                  │
│  └── cleanup_stale_war_rooms                                    │
├─────────────────────────────────────────────────────────────────┤
│  Data Layer (PostgreSQL)                                        │
│  ├── Incidents, Events, Comments                                │
│  ├── Teams, Services, ImpactScopes                              │
│  ├── Runbooks, EscalationPolicies                               │
│  └── NotificationProviders, AuditLogs                           │
└─────────────────────────────────────────────────────────────────┘
```

### Composants Docker

| Service | Description | Port |
|---------|-------------|------|
| `imas_web` | Application Django + Gunicorn | 8000 |
| `imas_worker` | Celery Worker (tâches async) | - |
| `imas_beat` | Celery Beat (tâches planifiées) | - |
| `imas_postgres` | Base de données PostgreSQL | 5432 |
| `imas_redis` | Broker Redis | 6379 |

---

## Cycle de Vie d'un Incident

### États (Status)

```
┌──────────────┐     ┌────────────────┐     ┌─────────────┐     ┌────────────┐
│   TRIGGERED  │ ──► │  ACKNOWLEDGED  │ ──► │  MITIGATED  │ ──► │  RESOLVED  │
│              │     │                │     │             │     │            │
│  (Détecté)   │     │   (Pris en     │     │  (Impact    │     │  (Résolu)  │
│              │     │    charge)     │     │   réduit)   │     │            │
└──────────────┘     └────────────────┘     └─────────────┘     └────────────┘
       │                                                               │
       │                     Escalade automatique                      │
       └───────────────────────────────────────────────────────────────┘
                            (si non acquitté)
```

### Niveaux de Sévérité

| Sévérité | Description | Actions Automatiques |
|----------|-------------|---------------------|
| **SEV1_CRITICAL** | Panne totale du service | War Room + SMS + Notifications immédiates |
| **SEV2_HIGH** | Dégradation majeure | War Room + Notifications Slack |
| **SEV3_MEDIUM** | Impact limité | Notifications Slack uniquement |
| **SEV4_LOW** | Mineur | Log + Ticket |

### Métriques KPI

- **MTTD (Mean Time To Detect)** : `created_at - detected_at`
- **MTTA (Mean Time To Acknowledge)** : `acknowledged_at - created_at`
- **MTTR (Mean Time To Resolve)** : `resolved_at - created_at`

---

## Workflow de Gestion des Incidents

### Workflow A : Création Manuelle (Interface Web)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CRÉATION VIA INTERFACE WEB                           │
└─────────────────────────────────────────────────────────────────────────┘

  Utilisateur                   Django                     Celery Worker
      │                           │                              │
      │  1. Remplit le formulaire │                              │
      │ ─────────────────────────►│                              │
      │                           │                              │
      │                           │  2. Validation + Création    │
      │                           │     Incident (TRIGGERED)     │
      │                           │                              │
      │                           │  3. Trigger async            │
      │                           │ ─────────────────────────────►
      │                           │                              │
      │  4. Redirection vers      │                              │
      │     page détail           │                              │
      │ ◄─────────────────────────│                              │
      │                           │                              │ 5. Orchestration
      │                           │                              │    - Créer LID
      │                           │                              │    - Créer War Room
      │                           │                              │    - Envoyer Notifs
      │                           │                              │
```

### Workflow B : Création Automatique (API/Monitoring)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CRÉATION VIA API (Monitoring)                        │
└─────────────────────────────────────────────────────────────────────────┘

  Monitoring Tool              API Django                  Celery Worker
  (Datadog, etc.)                  │                            │
      │                            │                            │
      │  POST /api/v1/incidents/   │                            │
      │ ──────────────────────────►│                            │
      │                            │                            │
      │                            │  1. Auth + Parsing         │
      │                            │                            │
      │                            │  2. Check Déduplication    │
      │                            │     ┌─────────────────┐    │
      │                            │     │ Incident existe │    │
      │                            │     │ pour ce service?│    │
      │                            │     └────────┬────────┘    │
      │                            │              │             │
      │                            │     OUI      │    NON      │
      │                            │   ┌─────────┴─────────┐    │
      │                            │   │                   │    │
      │                            │   ▼                   ▼    │
      │                            │ Return 200 OK    Create 201│
      │                            │ + existing ID    + new ID  │
      │                            │                            │
      │  Response immédiate        │                            │
      │ ◄──────────────────────────│                            │
      │                            │                            │
      │                            │  3. Trigger async ─────────►
      │                            │                            │
```

### Workflow C : Orchestration Asynchrone (Celery)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION (Tâche Celery)                         │
└─────────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────────────┐
  │  orchestrate_incident_task(incident_id)                            │
  ├────────────────────────────────────────────────────────────────────┤
  │                                                                    │
  │  1. RÉCUPÉRATION                                                   │
  │     └── Charger l'incident depuis la DB                            │
  │                                                                    │
  │  2. DOCUMENTATION (LID)                                            │
  │     ├── Copier le template Post-Mortem                             │
  │     ├── Renommer "INC-{short_id} - {title}"                        │
  │     ├── Sauvegarder le lien dans incident.lid_link                 │
  │     └── Log Event: "LID Created"                                   │
  │                                                                    │
  │  3. WAR ROOM (si Sévérité <= SEV2)                                 │
  │     ├── Créer canal Slack/Discord dédié                            │
  │     ├── Inviter: Lead + On-Call Team + Scopes concernés            │
  │     ├── Poster le message d'en-tête avec contexte                  │
  │     ├── Sauvegarder incident.war_room_link                         │
  │     └── Log Event: "War Room Created"                              │
  │                                                                    │
  │  4. RUNBOOK                                                        │
  │     ├── Rechercher le runbook lié au Service                       │
  │     └── Afficher les étapes de résolution                          │
  │                                                                    │
  │  5. NOTIFICATIONS                                                  │
  │     ├── Calculer les destinataires (NotificationRouter)            │
  │     │   ├── Team Owner du Service                                  │
  │     │   ├── On-Call de la Team                                     │
  │     │   └── Emails obligatoires des ImpactScopes                   │
  │     ├── Construire le message (titre, sévérité, liens)             │
  │     └── Envoyer via les canaux appropriés                          │
  │                                                                    │
  │  6. TERMINÉ                                                        │
  │     └── Log Event: "Orchestration Complete"                        │
  │                                                                    │
  └────────────────────────────────────────────────────────────────────┘
```

### Workflow D : Escalade Automatique

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ESCALADE AUTOMATIQUE                                 │
└─────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────┐
  │ check_pending_  │  (Tâche planifiée toutes les 5 min)
  │ escalations     │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────────────────────────────┐
  │  Pour chaque incident TRIGGERED         │
  │  (non acquitté)                         │
  └────────┬────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────┐
  │  Trouver la politique d'escalade        │
  │  (EscalationPolicy) de la Team          │
  └────────┬────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────┐
  │  Temps écoulé > Délai du Step ?         │
  │                                         │
  │    Step 1: 5 min  → Slack Channel       │
  │    Step 2: 15 min → On-Call SMS         │
  │    Step 3: 30 min → Manager Email       │
  └────────┬────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────┐
  │  Déclencher la notification             │
  │  d'escalade au niveau suivant           │
  └─────────────────────────────────────────┘
```

---

## Composants Principaux

### Modèles de Données

#### Organisation

| Modèle | Description |
|--------|-------------|
| `Team` | Équipe technique (ex: "SRE Core", "Backend Payment") |
| `Service` | Actif technique (ex: "Redis Cluster", "Checkout API") |
| `ImpactScope` | Impact transverse (ex: "Security", "GDPR/Legal", "PR") |
| `OnCallSchedule` | Planning des astreintes par équipe |

#### Incident

| Modèle | Description |
|--------|-------------|
| `Incident` | L'incident lui-même avec titre, description, sévérité, status |
| `IncidentEvent` | Timeline/Audit log de l'incident |
| `IncidentComment` | Commentaires et notes ajoutés par les intervenants |
| `IncidentTag` | Tags pour catégorisation et recherche |
| `IncidentEscalation` | Historique des escalades déclenchées |

#### Opérations

| Modèle | Description |
|--------|-------------|
| `Runbook` | Procédure de réparation liée à un service |
| `RunbookStep` | Étape individuelle d'un runbook |
| `EscalationPolicy` | Politique d'escalade pour une équipe |
| `EscalationStep` | Niveau d'escalade avec délai et destinataires |

#### Configuration

| Modèle | Description |
|--------|-------------|
| `NotificationProvider` | Configuration des canaux (Slack, SMS, Email, etc.) |
| `AlertSource` | Source d'alerte (Datadog, Prometheus, etc.) |
| `AlertRule` | Règle de mapping alerte → service |

### Services Métier

```python
# services/orchestrator.py
class IncidentOrchestrator:
    """Orchestrateur principal du cycle de vie incident"""
    
    def create_incident(data, user) -> Incident
    def deduplicate_check(service, severity) -> Incident | None
    def acknowledge_incident(incident, user) -> Incident
    def resolve_incident(incident, user, resolution_note) -> Incident

# services/notifications/router.py
class NotificationRouter:
    """Routage intelligent des notifications"""
    
    def calculate_recipients(incident) -> list[Recipient]
    def send_alert(incident, recipients) -> None

# services/escalation.py
class EscalationService:
    """Gestion des escalades automatiques"""
    
    def check_and_escalate(incident) -> bool
    def get_current_level(incident) -> int

# services/runbook.py
class RunbookService:
    """Gestion des runbooks"""
    
    def find_runbook(incident) -> Runbook | None
    def get_runbook_steps(runbook) -> list[Step]
    def execute_step(step, executor) -> Execution
```

---

## Fonctionnalités Clés

### 1. Déduplication des Alertes

Les outils de monitoring peuvent envoyer des dizaines d'alertes pour un même problème. IMAS Manager utilise un système de **fingerprinting** :

```python
# Logique de déduplication
existing = Incident.objects.filter(
    service=service,
    status__in=['TRIGGERED', 'ACKNOWLEDGED']
).first()

if existing:
    # Ajouter un event au lieu de créer un nouvel incident
    IncidentEvent.objects.create(
        incident=existing,
        type='ALERT_RECEIVED',
        message=f"Duplicate alert received from {source}"
    )
    return existing  # Retourner l'incident existant
```

### 2. Notification Intelligente

Le routeur de notifications détermine automatiquement **qui** notifier et **comment** :

| Condition | Canal | Destinataires |
|-----------|-------|---------------|
| SEV1 + On-Call défini | SMS | Personne d'astreinte |
| Team Owner | Slack | Canal de l'équipe |
| ImpactScope "Security" | Email | CISO + Equipe Sécu |
| ImpactScope "Legal" | Email | DPO |

### 3. War Room Automatique

Pour les incidents SEV1/SEV2, un canal de communication dédié est créé :

- **Nom** : `inc-{short_id}-{service_name}`
- **Invités** : Lead, On-Call, Teams concernées
- **Message initial** : Contexte, liens LID, liens Runbook

### 4. Runbooks Guidés

Les runbooks sont des procédures de réparation étape par étape :

```yaml
Runbook: "Redis Cluster Recovery"
Service: Redis Cluster
Steps:
  1. Vérifier les métriques de santé
     Commande: redis-cli cluster info
     Durée estimée: 2 min
     
  2. Identifier les nœuds défaillants
     Commande: redis-cli cluster nodes | grep fail
     Critique: Oui
     
  3. Failover manuel si nécessaire
     Commande: redis-cli cluster failover
     Rollback: redis-cli cluster failover abort
```

### 5. Escalade Automatique

Si un incident n'est pas acquitté dans les délais définis :

```
Temps     Action
─────────────────────────────────────
0 min     Création incident → Slack
5 min     Step 1 → Re-notification Slack
15 min    Step 2 → SMS à l'On-Call
30 min    Step 3 → Email au Manager
60 min    Step 4 → Notification CTO
```

---

## Déploiement

### Prérequis

- Docker / Podman
- Docker Compose / Podman Compose

### Démarrage Rapide

```bash
# 1. Cloner le dépôt
git clone https://github.com/SeeMyPing/imas-manager.git
cd imas-manager

# 2. Configurer les variables d'environnement
cp docker/.env.example docker/.env
# Éditer docker/.env avec vos valeurs

# 3. Démarrer les services
cd docker
podman compose up --build -d

# 4. Créer un superutilisateur
podman exec -it imas_web python manage.py createsuperuser

# 5. Accéder à l'application
open http://localhost:8000/dashboard/
```

### Vérification des Services

```bash
# Vérifier que tous les conteneurs tournent
podman ps

# Vérifier les logs
podman logs imas_web      # Application Django
podman logs imas_worker   # Celery Worker
podman logs imas_beat     # Celery Beat (tâches planifiées)
```

### Variables d'Environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `DEBUG` | Mode debug Django | False |
| `SECRET_KEY` | Clé secrète Django | (obligatoire) |
| `ALLOWED_HOSTS` | Hosts autorisés | localhost,127.0.0.1 |
| `DATABASE_URL` | URL PostgreSQL | postgres://... |
| `CELERY_BROKER_URL` | URL Redis | redis://redis:6379/0 |

---

## API Reference

### Endpoints Principaux

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/api/v1/incidents/` | Créer un incident |
| `GET` | `/api/v1/incidents/` | Lister les incidents |
| `GET` | `/api/v1/incidents/{id}/` | Détail d'un incident |
| `PATCH` | `/api/v1/incidents/{id}/acknowledge/` | Acquitter |
| `PATCH` | `/api/v1/incidents/{id}/resolve/` | Résoudre |
| `GET` | `/api/v1/services/` | Catalogue de services |
| `GET` | `/api/v1/metrics/` | Métriques KPI |

### Exemple : Création d'Incident via API

```bash
curl -X POST http://localhost:8000/api/v1/incidents/ \
  -H "Authorization: Token YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Redis Cluster Down",
    "description": "All nodes reporting connection timeout",
    "service_name": "redis-prod",
    "severity": "SEV1_CRITICAL",
    "detected_at": "2026-02-05T18:30:00Z"
  }'
```

### Documentation OpenAPI

La documentation interactive Swagger est disponible sur :
- **Swagger UI** : `http://localhost:8000/api/docs/`
- **ReDoc** : `http://localhost:8000/api/redoc/`

---

## Configuration

### Configuration des Providers de Notification

Accédez à l'admin Django (`/admin/`) pour configurer les providers :

#### Slack

```json
{
  "bot_token": "xoxb-your-bot-token",
  "default_channel": "C0123456789"
}
```

#### OVH SMS

```json
{
  "application_key": "your-app-key",
  "application_secret": "your-app-secret",
  "consumer_key": "your-consumer-key",
  "service_name": "sms-xxxxx-1",
  "sender": "IMAS"
}
```

#### Email (SMTP)

```json
{
  "host": "smtp.example.com",
  "port": 587,
  "username": "alerts@example.com",
  "password": "your-password",
  "use_tls": true
}
```

---

## Bonnes Pratiques

### Pour les Opérateurs

1. **Acquitter rapidement** : Dès que vous prenez connaissance d'un incident, acquittez-le pour stopper les escalades.

2. **Documenter en temps réel** : Utilisez les commentaires pour noter vos actions. Le LID sera pré-rempli.

3. **Suivre les runbooks** : Les runbooks sont là pour guider. Marquez chaque étape comme complétée.

4. **Inviter les bonnes personnes** : Si vous avez besoin d'aide, invitez d'autres personnes dans la War Room.

### Pour les Administrateurs

1. **Maintenir le catalogue de services** : Un bon mapping service → équipe est essentiel pour le routage.

2. **Configurer les escalades** : Définissez des politiques d'escalade réalistes (pas trop agressives).

3. **Créer des runbooks** : Chaque service critique devrait avoir un runbook associé.

4. **Réviser les KPIs** : Analysez régulièrement les métriques MTTD/MTTA/MTTR pour améliorer les processus.

### Pour l'Intégration

1. **Utiliser l'API pour le monitoring** : Configurez vos outils de monitoring pour envoyer les alertes via l'API.

2. **Activer la déduplication** : Assurez-vous que le `service_name` est cohérent dans les alertes.

3. **Configurer les webhooks** : Les webhooks sortants permettent d'intégrer IMAS avec d'autres outils.

---

## Documents Complémentaires

- [01_project_scope.md](01_project_scope.md) - Vision et périmètre du projet
- [02_data_models.md](02_data_models.md) - Spécifications des modèles de données
- [03_business_logic.md](03_business_logic.md) - Logique métier et services
- [04_workflow.md](04_workflow.md) - Diagrammes de séquence détaillés

---

## Support

- **GitHub Issues** : https://github.com/SeeMyPing/imas-manager/issues
- **Documentation API** : http://localhost:8000/api/docs/

---

*Documentation générée le 5 février 2026 - IMAS Manager v1.0*
