# IMAS Manager (Incident Management At Scale)

IMAS Manager est une plateforme d'orchestration de réponse aux incidents techniques majeurs. Elle centralise la détection, la communication (War Room), la documentation (LID) et l'analyse post-incident.

## 🚀 Démarrage Rapide

### Prérequis
- Python 3.11+
- Redis (pour Celery)
- PostgreSQL (ou SQLite pour le dev)

### Installation

1.  **Cloner le dépôt :**
    ```bash
    git clone https://github.com/SeeMyPing/imas-manager.git
    cd imas-manager
    ```

2.  **Configurer l'environnement virtuel :**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Variables d'Environnement :**
    Créez un fichier `.env` à la racine de `app/` (voir `app/.env.example` s'il existe).
    ```bash
    cp app/.env.example app/.env
    ```

4.  **Migrations DB :**
    ```bash
    cd app
    python manage.py migrate
    ```

5.  **Créer un Superuser :**
    ```bash
    python manage.py createsuperuser
    ```

### Lancer le Serveur de Développement
```bash
python manage.py runserver
```

Le dashboard sera accessible sur ``http://localhost:8000/dashboard/``.

---

## ⚡ Tâches Asynchrones (Celery)

IMAS Manager utilise Celery pour orchestrer les actions bloquantes (création GDocs, Slack channels, notifications).

### Lancer un Worker Celery
Assurez-vous d'avoir un serveur Redis accessible (par défaut `localhost:6379`).

```bash
cd app
celery -A config worker --loglevel=info
```

### Lancer le Scheduler (Celery Beat)
Pour les tâches périodiques (escalades, rappels, archivage).

```bash
cd app
celery -A config beat -l info
```

---

## 🧪 Tests

```bash
cd app
pytest
# Ou avec Django test runner
python manage.py test
```

## 🏗 Structure du Projet

- `app/` : Code source Django
  - `core/` : Modèles de données principaux
  - `dashboard/` : Interface Web
  - `api/` : API REST (DRF)
  - `services/` : Logique métier (Google Drive, Slack, Notifications)
  - `tasks/` : Tâches asynchrones Celery
  - `integrations/` : Clients externes
- `docs/` : Documentation fonctionnelle et technique
- `docker/` : Configuration conteneurs

---

## 📦 Étapes de Développement

- [x] Phase 1-10 : Core, API, Services
- [x] Phase 11 : Dashboard Web
- [x] Phase 12 : Configuration Celery & Async Tasks
- [ ] Phase 13 : Docker & Déploiement
