# Workflows & Sequence Diagrams

Ce document détaille les flux d'exécution (Synchrones vs Asynchrones) pour les deux points d'entrée principaux de l'application.

## 1. Workflow A : Création via Interface Web (Human Driven)
*Utilisé lorsqu'un humain détecte un problème non monitoré ou souhaite déclarer un incident manuellement.*

### Séquence :
1.  **Formulaire :** L'utilisateur remplit le formulaire de création (`CreateIncidentForm`).
    - Champs : Titre, Description, Service (Dropdown), Sévérité, Impacted Scopes (Checkbox).
2.  **Validation (Synchrone) :**
    - Django vérifie que les champs obligatoires sont présents.
    - Vérifie que l'utilisateur a les droits (`permission_required`).
3.  **Sauvegarde Initiale :**
    - Création de l'objet `Incident` en DB avec status `TRIGGERED`.
    - `created_at` est défini automatiquement.
    - `lead` est assigné à l'utilisateur courant (request.user).
4.  **Trigger Async :**
    - Appel de `orchestrate_incident_task.delay(incident_id)`.
5.  **Feedback Utilisateur :**
    - Redirection immédiate vers la page de détail de l'incident (`IncidentDetailView`).
    - Affichage d'un message Flash : *"Incident créé. La War Room et le Document sont en cours de génération..."*.
    - L'interface affiche des "placeholders" ou des spinners pour les liens LID/Slack tant qu'ils ne sont pas générés.

## 2. Workflow B : Création via API (Machine Driven / Monitoring)
*Utilisé par Datadog, Prometheus, AlertManager, Sentry, etc.*

### Concepts Clés : Déduplication & Mapping
Contrairement au web, l'API doit gérer le bruit.
- **Service Mapping :** Le payload JSON contient souvent un nom de service (ex: "redis-prod") et non un UUID. Le système doit faire le lookup `Service.objects.get(name="redis-prod")`. Si non trouvé -> Assigner au service "Unknown/Triage".
- **Déduplication (Alert Fingerprinting) :**
    - Si un incident est déjà `OPEN` ou `TRIGGERED` pour ce même Service avec une sévérité similaire, on ne crée pas de nouvel incident.
    - On ajoute simplement une entrée dans `IncidentEvent` (Log) pour dire "Alerte reçue de nouveau".

### Séquence API (`POST /api/v1/incidents/`) :
1.  **Auth :** Validation du Token API.
2.  **Parsing & Lookup :**
    - Extraction du `service_name`. Recherche du `Service` correspondant en DB.
3.  **Check Déduplication :**
    - `Incident.objects.filter(service=service, status__in=['TRIGGERED', 'ACKNOWLEDGED'])`
    - **SI EXISTE :** Retourner `200 OK` + ID de l'incident existant (Idempotence). Ajouter un log dans `IncidentEvent`.
    - **SI NOUVEAU :** Créer l'objet `Incident`.
4.  **Réponse API :**
    - Retourner `201 Created` JSON immédiatement (ne pas attendre Slack/Drive).
5.  **Trigger Async :**
    - Appel de `orchestrate_incident_task.delay(incident_id)`.

## 3. Workflow C : L'Orchestrateur (Tâche Celery)
*Ce workflow est commun aux deux méthodes d'entrée. Il s'exécute en arrière-plan.*

```ascii
[ Worker Celery ]
      |
      +---> 1. DÉMARRAGE
      |      Recupère l'incident par ID
      |
      +---> 2. GESTION DU DOCUMENT (LID)
      |      Appel GDriveService.create_doc()
      |      Update Incident.lid_link
      |      Log Event: "LID Created"
      |
      +---> 3. GESTION WAR ROOM (Si Sev <= 2)
      |      Appel ChatOps.create_channel("inc-123")
      |      Appel ChatOps.invite([Lead, TeamOnCall, SecuOnCall])
      |      Update Incident.war_room_link
      |
      +---> 4. NOTIFICATION (Broadcast)
      |      Construction du message (avec les liens LID/WarRoom générés ci-dessus)
      |      Calcul des destinataires (Router)
      |      Envoi SMS / Slack / Email
      |
      +---> 5. TERMINÉ
             Log Event: "Orchestration finished"