# Guide des Runbooks & Escalades

> Configuration et bonnes pratiques pour les runbooks et les politiques d'escalade

---

## 📋 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Runbooks](#runbooks)
   - [Qu'est-ce qu'un Runbook ?](#quest-ce-quun-runbook)
   - [Création d'un Runbook](#création-dun-runbook)
   - [Structure des Étapes](#structure-des-étapes)
   - [Bonnes Pratiques](#bonnes-pratiques-runbooks)
   - [Exemples de Runbooks](#exemples-de-runbooks)
3. [Escalades](#escalades)
   - [Qu'est-ce qu'une Escalade ?](#quest-ce-quune-escalade)
   - [Politiques d'Escalade](#politiques-descalade)
   - [Configuration des Steps](#configuration-des-steps)
   - [Bonnes Pratiques](#bonnes-pratiques-escalades)
4. [Workflow Complet](#workflow-complet)

---

## Vue d'ensemble

### Pourquoi les Runbooks et Escalades ?

```
┌─────────────────────────────────────────────────────────────────┐
│                      Incident Déclenché                          │
└─────────────────────────────────────────────────────────────────┘
                               │
           ┌───────────────────┴───────────────────┐
           ▼                                       ▼
┌─────────────────────┐                 ┌─────────────────────┐
│      RUNBOOK        │                 │      ESCALADE       │
│                     │                 │                     │
│ "Comment réparer ?" │                 │ "Qui prévenir si    │
│                     │                 │  personne ne        │
│ Guide étape par     │                 │  répond ?"          │
│ étape pour          │                 │                     │
│ résoudre            │                 │ Notifications       │
│ l'incident          │                 │ automatiques        │
│                     │                 │ progressives        │
└─────────────────────┘                 └─────────────────────┘
```

---

## Runbooks

### Qu'est-ce qu'un Runbook ?

Un runbook est une procédure documentée, étape par étape, pour diagnostiquer et résoudre un type d'incident spécifique.

**Avantages :**
- ✅ Réponse standardisée et reproductible
- ✅ Temps de résolution réduit (MTTR)
- ✅ Moins de dépendance aux experts
- ✅ Documentation automatique des actions
- ✅ Onboarding facilité pour les nouveaux

### Création d'un Runbook

#### Via l'Admin Django

1. **Admin** → **Core** → **Runbooks** → **Add Runbook**

| Champ | Description | Exemple |
|-------|-------------|---------|
| Title | Nom du runbook | `Redis Cluster Recovery` |
| Description | Description générale | `Procédure de récupération d'un cluster Redis` |
| Service | Service associé (optionnel) | `redis-prod` |
| Severity Filter | Sévérité ciblée (optionnel) | `SEV1_CRITICAL` |
| Is Active | Activer le runbook | ✅ |

#### Via l'API

```bash
POST /api/v1/runbooks/
Authorization: Token <your-token>

{
  "title": "Redis Cluster Recovery",
  "description": "Procédure de récupération d'un cluster Redis en échec",
  "service": "550e8400-e29b-41d4-a716-446655440000",
  "severity_filter": "SEV1_CRITICAL",
  "is_active": true
}
```

### Structure des Étapes

Chaque runbook contient des étapes ordonnées :

#### Ajouter des Étapes

1. **Admin** → **Core** → **Runbook Steps** → **Add Runbook Step**

| Champ | Description | Exemple |
|-------|-------------|---------|
| Runbook | Runbook parent | `Redis Cluster Recovery` |
| Order | Numéro d'ordre | `1` |
| Title | Titre de l'étape | `Vérifier le statut du cluster` |
| Description | Instructions détaillées | `Exécuter la commande ci-dessous...` |
| Command | Commande à exécuter (optionnel) | `redis-cli cluster info` |
| Expected Duration | Durée estimée (minutes) | `2` |
| Is Critical | Étape critique ? | ❌ |
| Requires Confirmation | Demander confirmation ? | ❌ |
| Rollback Instructions | Instructions de rollback | `Si erreur, voir étape 5` |

#### Champs des Étapes

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: Vérifier le statut du cluster                          │
├─────────────────────────────────────────────────────────────────┤
│  Description:                                                    │
│  Avant toute intervention, vérifier l'état actuel du cluster    │
│  Redis pour comprendre la nature du problème.                   │
│                                                                  │
│  Command:                                                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ redis-cli -h redis-master -p 6379 cluster info             ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ⏱️ Durée estimée: 2 minutes                                     │
│  ⚠️ Critique: Non                                                │
│  ✅ Confirmation requise: Non                                    │
│                                                                  │
│  Rollback:                                                       │
│  N/A - Étape de diagnostic uniquement                           │
└─────────────────────────────────────────────────────────────────┘
```

### Bonnes Pratiques Runbooks

#### 1. Structure Claire

```
✅ BON:
Step 1: Diagnostiquer
Step 2: Isoler
Step 3: Réparer
Step 4: Vérifier
Step 5: Communiquer

❌ MAUVAIS:
Step 1: Faire plein de trucs
Step 2: Espérer que ça marche
```

#### 2. Commandes Complètes

```yaml
# ✅ BON - Commande complète avec contexte
Command: |
  # Se connecter au pod Redis master
  kubectl exec -it redis-master-0 -n production -- redis-cli cluster info

# ❌ MAUVAIS - Commande sans contexte
Command: redis-cli cluster info
```

#### 3. Checklist de Vérification

Chaque runbook devrait inclure une étape de vérification finale :

```yaml
Step N: Vérification Post-Résolution

Description: |
  Vérifier que le service est complètement restauré :
  - [ ] Toutes les métriques sont vertes
  - [ ] Pas d'erreurs dans les logs (5 dernières minutes)
  - [ ] Les requêtes clients passent correctement
  - [ ] Les alertes monitoring sont fermées

Command: |
  # Vérifier les métriques
  curl -s http://redis-master:9121/metrics | grep cluster_state
  
  # Vérifier les logs
  kubectl logs redis-master-0 --tail=50 | grep -i error
```

#### 4. Instructions de Rollback

Pour chaque étape qui modifie l'état, documenter le rollback :

```yaml
Step 3: Effectuer le failover

Command: redis-cli cluster failover

Rollback Instructions: |
  Si le failover échoue ou cause des problèmes :
  1. Annuler le failover : redis-cli cluster failover abort
  2. Vérifier l'état : redis-cli cluster info
  3. Contacter l'équipe DBA si le cluster reste instable
```

#### 5. Durées Réalistes

Estimer des durées réalistes pour chaque étape :

| Type d'étape | Durée typique |
|--------------|---------------|
| Diagnostic | 2-5 min |
| Commande simple | 1-2 min |
| Redémarrage service | 5-10 min |
| Failover DB | 10-30 min |
| Vérification | 5 min |

### Exemples de Runbooks

#### Exemple 1 : Redis Cluster Recovery

```yaml
Title: Redis Cluster Recovery
Service: redis-prod
Severity: SEV1_CRITICAL

Steps:
  1:
    title: Évaluer l'état du cluster
    description: |
      Vérifier l'état actuel du cluster Redis pour identifier
      le type de panne (nœud down, réseau, mémoire).
    command: |
      # État global
      redis-cli -h redis-master cluster info
      
      # État des nœuds
      redis-cli -h redis-master cluster nodes | grep -E "(fail|myself)"
    duration: 2
    critical: false

  2:
    title: Identifier les nœuds en échec
    description: |
      Lister tous les nœuds marqués comme "fail" ou "pfail".
    command: |
      redis-cli -h redis-master cluster nodes | grep fail
    duration: 2
    critical: false

  3:
    title: Vérifier la connectivité réseau
    description: |
      S'assurer que les nœuds peuvent communiquer entre eux.
    command: |
      # Ping depuis chaque nœud
      for node in redis-0 redis-1 redis-2; do
        kubectl exec -it $node -- redis-cli ping
      done
    duration: 3
    critical: false

  4:
    title: Effectuer un failover si nécessaire
    description: |
      Si le master est down, promouvoir un replica.
      ⚠️ Cette opération peut causer une courte interruption.
    command: |
      redis-cli -h redis-replica-0 cluster failover takeover
    duration: 5
    critical: true
    requires_confirmation: true
    rollback: |
      redis-cli cluster failover abort
      
      Si le cluster reste instable :
      kubectl rollout restart statefulset/redis

  5:
    title: Vérifier la récupération
    description: |
      Confirmer que le cluster est de nouveau fonctionnel.
    command: |
      # Vérifier l'état
      redis-cli cluster info | grep cluster_state
      
      # Tester les opérations
      redis-cli set test-key "recovery-test"
      redis-cli get test-key
      redis-cli del test-key
    duration: 3
    critical: false

  6:
    title: Notifier la résolution
    description: |
      Mettre à jour le status de l'incident et notifier les parties prenantes.
      
      Checklist :
      - [ ] Incident marqué comme résolu
      - [ ] Cause root documentée
      - [ ] Métriques monitoring vérifiées
      - [ ] Communication envoyée si client impacté
    duration: 5
    critical: false
```

#### Exemple 2 : API Gateway High Latency

```yaml
Title: API Gateway High Latency Investigation
Service: api-gateway
Severity: SEV2_HIGH

Steps:
  1:
    title: Identifier la source de latence
    description: |
      Vérifier les métriques pour identifier si la latence vient
      de l'API Gateway ou d'un service en aval.
    command: |
      # Métriques Prometheus
      curl -s "http://prometheus:9090/api/v1/query?query=http_request_duration_seconds_bucket"
      
      # Logs récents
      kubectl logs -l app=api-gateway --tail=100 | grep -i "slow\|timeout"
    duration: 5

  2:
    title: Vérifier les ressources
    description: |
      S'assurer que les pods ont suffisamment de CPU/mémoire.
    command: |
      kubectl top pods -l app=api-gateway
      kubectl describe hpa api-gateway
    duration: 3

  3:
    title: Vérifier les services en aval
    description: |
      Identifier si un service backend cause la latence.
    command: |
      # Latence par service
      curl -s "http://prometheus:9090/api/v1/query?query=upstream_response_time_seconds"
    duration: 5

  4:
    title: Scaling horizontal si nécessaire
    description: |
      Augmenter le nombre de replicas si le problème est lié à la charge.
    command: |
      kubectl scale deployment api-gateway --replicas=10
    duration: 5
    requires_confirmation: true
    rollback: |
      kubectl scale deployment api-gateway --replicas=3

  5:
    title: Vérifier l'amélioration
    description: |
      Confirmer que la latence est revenue à la normale.
    command: |
      # Attendre 2 minutes et vérifier
      sleep 120
      curl -s "http://prometheus:9090/api/v1/query?query=http_request_duration_seconds_bucket"
    duration: 5
```

---

## Escalades

### Qu'est-ce qu'une Escalade ?

L'escalade automatique notifie progressivement différentes personnes si un incident n'est pas acquitté dans un délai défini.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Timeline d'Escalade                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  T+0        T+5min      T+15min     T+30min     T+60min         │
│   │           │           │           │           │              │
│   ▼           ▼           ▼           ▼           ▼              │
│ Incident   Step 1:     Step 2:     Step 3:     Step 4:          │
│ Créé       Slack       SMS         Email       CTO              │
│            #team       On-Call     Manager     Notification     │
│                                                                  │
│            ─────────────────────────────────────────────────►    │
│            Si non acquitté, passer au step suivant              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Politiques d'Escalade

#### Créer une Politique

1. **Admin** → **Core** → **Escalation Policies** → **Add**

| Champ | Description | Exemple |
|-------|-------------|---------|
| Name | Nom de la politique | `SRE Core - SEV1` |
| Team | Équipe associée | `SRE Core` |
| Severity Filter | Sévérité ciblée | `SEV1_CRITICAL` |
| Is Active | Activer | ✅ |
| Is Default | Politique par défaut pour la team | ❌ |

#### Hiérarchie des Politiques

```
Team: SRE Core
│
├── Politique "SRE Core - SEV1" (severity_filter: SEV1_CRITICAL)
│   └── Utilisée pour les incidents SEV1
│
├── Politique "SRE Core - SEV2" (severity_filter: SEV2_HIGH)
│   └── Utilisée pour les incidents SEV2
│
└── Politique "SRE Core - Default" (is_default: true)
    └── Utilisée pour SEV3, SEV4 et tout autre cas
```

### Configuration des Steps

#### Ajouter des Steps d'Escalade

1. **Admin** → **Core** → **Escalation Steps** → **Add**

| Champ | Description | Exemple |
|-------|-------------|---------|
| Policy | Politique parente | `SRE Core - SEV1` |
| Step Order | Ordre du step | `1` |
| Delay Minutes | Délai avant ce step | `5` |
| Notification Type | Type de notification | `SLACK`, `SMS`, `EMAIL` |
| Target Type | Cible | `ON_CALL`, `TEAM`, `USER`, `EMAIL` |
| Target User | Utilisateur spécifique (si USER) | `john.doe` |
| Target Email | Email spécifique (si EMAIL) | `manager@example.com` |
| Is Active | Activer ce step | ✅ |

#### Types de Notification

| Type | Description | Cas d'usage |
|------|-------------|-------------|
| `SLACK` | Message Slack | Steps 1-2, notifications légères |
| `SMS` | SMS via OVH | Steps 2-3, urgence |
| `EMAIL` | Email | Management, stakeholders |
| `PHONE` | Appel téléphonique | Dernier recours (nécessite intégration) |

#### Types de Cible

| Target Type | Description |
|-------------|-------------|
| `ON_CALL` | Personne d'astreinte de la team |
| `TEAM` | Tous les membres de la team |
| `USER` | Utilisateur spécifique |
| `EMAIL` | Adresse email externe |
| `CHANNEL` | Canal Slack/Discord |

### Exemple de Politique Complète

```yaml
Policy: SRE Core - SEV1
Team: SRE Core
Severity: SEV1_CRITICAL

Steps:
  Step 1:
    delay: 0 minutes
    type: SLACK
    target: CHANNEL (#sre-incidents)
    message: |
      🚨 Nouvel incident SEV1 créé
      Titre: {incident.title}
      Service: {incident.service}
      → Acquitter dans les 5 prochaines minutes

  Step 2:
    delay: 5 minutes
    type: SLACK + SMS
    target: ON_CALL
    message: |
      ⚠️ ESCALADE: Incident SEV1 non acquitté depuis 5 min
      {incident.short_id}: {incident.title}

  Step 3:
    delay: 15 minutes
    type: SMS + EMAIL
    target: USER (team_lead)
    message: |
      🔴 ESCALADE NIVEAU 2: {incident.short_id}
      Non acquitté depuis 15 minutes
      On-Call ne répond pas

  Step 4:
    delay: 30 minutes
    type: EMAIL + SLACK
    target: EMAIL (engineering-manager@company.com)
    message: |
      🆘 ESCALADE NIVEAU 3
      Incident SEV1 non géré depuis 30 minutes
      Action immédiate requise

  Step 5:
    delay: 60 minutes
    type: EMAIL + SMS
    target: EMAIL (cto@company.com)
    message: |
      🚨 ESCALADE DIRECTION
      Incident critique non résolu depuis 1 heure
      Intervention direction requise
```

### Bonnes Pratiques Escalades

#### 1. Délais Progressifs

```
✅ BON:
Step 1: 0 min  (notification immédiate)
Step 2: 5 min  (premier rappel)
Step 3: 15 min (escalade niveau 2)
Step 4: 30 min (escalade management)

❌ MAUVAIS:
Step 1: 0 min
Step 2: 1 min  (trop rapide, spam)
Step 3: 2 min
Step 4: 3 min
```

#### 2. Canaux Appropriés

| Urgence | Canal |
|---------|-------|
| Faible | Slack uniquement |
| Moyenne | Slack + Email |
| Haute | Slack + SMS |
| Critique | SMS + Appel |

#### 3. Pas Trop de Steps

```
✅ BON: 3-5 steps maximum
❌ MAUVAIS: 10+ steps (fatigue d'alerte)
```

#### 4. Documenter les Attentes

```yaml
# Dans la description de la politique
Description: |
  Cette politique s'applique aux incidents SEV1 de l'équipe SRE.
  
  Attentes:
  - Step 1 (0 min): Information de l'équipe
  - Step 2 (5 min): L'on-call doit acquitter
  - Step 3 (15 min): Le lead doit intervenir
  - Step 4 (30 min): Le manager doit coordonner
  
  Si Step 4 est atteint, un post-mortem est obligatoire.
```

---

## Workflow Complet

### Scénario : Incident Redis SEV1

```
┌─────────────────────────────────────────────────────────────────┐
│                    T+0: Incident Créé                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Alertmanager envoie webhook à IMAS                          │
│  2. Incident créé: INC-ABC123 - Redis Cluster Down              │
│  3. Runbook "Redis Cluster Recovery" attaché automatiquement    │
│  4. Notification Slack envoyée à #sre-incidents                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    T+5: Escalade Step 2                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ❌ Incident non acquitté                                        │
│  → SMS envoyé à l'on-call (John Doe)                            │
│  → Message Slack direct à @john.doe                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    T+8: Acquittement                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ✅ John acquitte l'incident via Slack                          │
│  → Escalade stoppée                                             │
│  → Status: ACKNOWLEDGED                                          │
│  → Runbook affiché dans le dashboard                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    T+10 → T+25: Résolution                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  John suit le runbook:                                          │
│  ✅ Step 1: Évaluer l'état (2 min)                              │
│  ✅ Step 2: Identifier nœuds en échec (2 min)                   │
│  ✅ Step 3: Vérifier connectivité (3 min)                       │
│  ✅ Step 4: Failover effectué (5 min)                           │
│  ✅ Step 5: Vérification OK (3 min)                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    T+30: Résolu                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ✅ Incident résolu par John                                    │
│  → Resolution note ajoutée                                      │
│  → MTTR: 30 minutes                                             │
│  → Notification de résolution envoyée                           │
│  → War Room archivée                                            │
│                                                                  │
│  KPIs:                                                          │
│  - MTTD: 0 min (alerte automatique)                             │
│  - MTTA: 8 min                                                  │
│  - MTTR: 30 min                                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

*Documentation générée le 5 février 2026 - IMAS Manager v1.0*
