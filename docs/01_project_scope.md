# Project Scope: IMAS Manager (Incident Management At Scale)

## 1. Vision du Produit
Créer une plateforme backend et dashboard pour gérer des incidents techniques majeurs. L'application ne se contente pas de logger des erreurs, elle orchestre la réponse à incident ("Response Orchestration"). Elle centralise la détection, la notification ciblée (astreintes), la collaboration (War Room), la documentation légale/technique (LID) et l'analyse post-incident (KPIs).

## 2. Stack Technique
- **Language:** Python 3.11+
- **Framework Web:** Django 5.x (Admin + Custom Dashboard)
- **API:** Django REST Framework (DRF) - Pour l'ingestion d'alertes et le frontend.
- **Database:** PostgreSQL (Critique pour la fiabilité relationnelle).
- **Async/Queue:** Celery + Redis (Indispensable pour l'orchestration non-bloquante).
- **Deployment:** Docker / Docker Compose.
- **Implementation:** L'application sera dans app/, la documentation dans docs/, tous les fichiers concernant le conteneur docker dans docker/. L'environnement virtual a sourcer pour travailler est dans .venv/

## 3. Fonctionnalités Clés
### A. Ingestion & Qualification
- Création d'incident via API (Monitoring tools) ou Interface Web.
- Qualification via **Service Catalog** (Quel composant est cassé ?).
- Qualification via **Impact Scopes** (Est-ce que le Légal, la Sécurité ou la PR sont touchés ?).

### B. Automation & Orchestration (Le cœur du système)
- **LID (Lead Incident Document) :** Création automatique d'un Google Doc (Post-Mortem template) via API Drive.
- **War Room :** Création automatique d'un canal dédié (Slack/Discord) pour les incidents critiques.
- **Runbooks :** Affichage automatique des procédures de réparation liées au Service impacté.

### C. Notification Intelligente (Smart Alerting)
- **Multi-canal :** Slack, Discord, SMS (OVH), Email (SMTP/Scaleway TEM).
- **Routage Ciblé :**
    - Si "Database" casse -> Notifier l'équipe "Infrastructure".
    - Si "Security Scope" touché -> Notifier le CISO et l'équipe Secu.
- **Escalade :** Support basique des astreintes (On-Call).

### D. Métriques & Suivi
- Audit Log complet (Timeline).
- Calcul automatique des KPIs : MTTD (Detection), MTTA (Ack), MTTR (Recovery).