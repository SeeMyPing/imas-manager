# Business Logic & Services

L'architecture doit suivre une approche "Service Layer" pour garder les Vues (Views) légères.

## 1. Orchestration (`services/orchestrator.py`)
Ce service gère le workflow principal.

### Méthode : `create_incident(data)`
1.  Valide les données et crée l'objet `Incident` en base.
2.  **Appel Async :** Déclenche la tâche Celery `setup_incident_task`.

### Tâche Celery : `setup_incident_task(incident_id)`
Exécute en parallèle (ou séquentiel non-bloquant) :
1.  **LID :** Appelle `GDriveService` pour copier le template, le renommer "INC-{id}", et sauver le lien dans l'incident.
2.  **War Room :** Si Sévérité <= SEV2, appelle `ChatOpsService` pour créer un canal Slack dédié et inviter le Lead + On-Call de la Team propriétaire.
3.  **Notifications :** Appelle `NotificationRouter` pour diffuser l'alerte.

## 2. Notification Router (`services/notifications/router.py`)
Logique de routage intelligent ("Qui prévenir ?").

### Logique d'agrégation des destinataires :
1.  **Destinataires Techniques :**
    - Récupérer `incident.service.owner_team`.
    - Ajouter le `current_on_call` de cette équipe (SMS si SEV1, Slack sinon).
    - Ajouter le canal Slack public de l'équipe.
2.  **Destinataires Fonctionnels (Scopes) :**
    - Parcourir `incident.impacted_scopes`.
    - Si un scope a un `mandatory_notify_email`, ajouter cet email à la liste d'envoi.
    - Si le scope est "Security", ajouter le groupe d'astreinte Sécurité (si défini).

### Exécution :
- Instancier les bons `Provider` (Slack, SMS, Mail) via un Factory Pattern basé sur le modèle `NotificationProvider`.
- Envoyer les messages contenant : Titre, Sévérité, **Lien Runbook**, Lien LID, Lien War Room.

## 3. Services Tiers

### `ChatOpsService` (Slack/Discord)
- Interface générique.
- Capacité à créer des canaux (`channels.create`).
- Capacité à inviter des utilisateurs par email (`users.lookupByEmail` -> `conversations.invite`).
- Capacité à poster le premier message "Incident Header" dans la War Room.

### `GDriveService`
- Authentification via Service Account (JSON file).
- Utilisation de Google Drive API v3.
- Gestion des permissions (Writer pour l'équipe technique, Reader pour le reste).

## 4. Calcul des KPIs (`signals.py`)
Utiliser les signaux Django `pre_save` ou `post_save` sur le modèle `Incident`.
- Si `status` passe de TRIGGERED à ACKNOWLEDGED -> set `acknowledged_at = now`.
- Si `status` passe à RESOLVED -> set `resolved_at = now`.
- `MTTD` = `created_at` - `detected_at`.
- `MTTR` = `resolved_at` - `created_at`.