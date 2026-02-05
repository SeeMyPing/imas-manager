# Guide de Contribution

> Contribuer au développement d'IMAS Manager

---

## 📋 Table des Matières

1. [Prérequis](#prérequis)
2. [Setup de l'Environnement](#setup-de-lenvironnement)
3. [Structure du Projet](#structure-du-projet)
4. [Standards de Code](#standards-de-code)
5. [Tests](#tests)
6. [Git Workflow](#git-workflow)
7. [Pull Requests](#pull-requests)
8. [Documentation](#documentation)
9. [Releases](#releases)

---

## Prérequis

### Outils Requis

| Outil | Version | Installation |
|-------|---------|--------------|
| Python | 3.11+ | `brew install python@3.11` |
| Poetry ou pip | Latest | `pip install poetry` |
| Redis | 7+ | `brew install redis` |
| PostgreSQL | 16+ | `brew install postgresql@16` |
| pre-commit | Latest | `pip install pre-commit` |

### Outils Recommandés

- **VS Code** avec extensions Python, Ruff
- **Docker Desktop** ou **Podman**
- **GitHub CLI** : `gh`

---

## Setup de l'Environnement

### 1. Fork et Clone

```bash
# Fork via GitHub UI, puis :
git clone https://github.com/YOUR-USERNAME/imas-manager.git
cd imas-manager

# Ajouter le remote upstream
git remote add upstream https://github.com/SeeMyPing/imas-manager.git
```

### 2. Environnement Virtuel

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 3. Installer les Dépendances

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 4. Pre-commit Hooks

```bash
pre-commit install
```

### 5. Variables d'Environnement

```bash
cd app
cp .env.example .env
```

Éditer `.env` :

```bash
DEBUG=True
SECRET_KEY=dev-secret-key-not-for-production
DATABASE_URL=sqlite:///db.sqlite3
CELERY_BROKER_URL=redis://localhost:6379/0
```

### 6. Migrations et Données de Test

```bash
cd app
python manage.py migrate
python manage.py createsuperuser
python manage.py loaddata fixtures/dev_data.json  # Si disponible
```

### 7. Lancer les Services

```bash
# Terminal 1 : Django
python manage.py runserver

# Terminal 2 : Celery (optionnel)
celery -A config worker --loglevel=info
```

---

## Structure du Projet

```
imas-manager/
├── .github/                    # GitHub Actions, templates
│   ├── workflows/
│   │   ├── ci.yml             # CI Pipeline
│   │   └── release.yml        # Release automation
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
│
├── app/                        # Application Django
│   ├── api/                   # API REST (DRF)
│   │   ├── auth/             # Authentification
│   │   └── v1/               # API v1
│   │
│   ├── config/               # Configuration Django
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── celery.py
│   │
│   ├── core/                 # Modèles et logique core
│   │   ├── models/          # Modèles Django
│   │   ├── signals.py       # Signaux Django
│   │   └── tasks.py         # Tâches Celery
│   │
│   ├── dashboard/           # Interface Web
│   │   ├── views.py
│   │   ├── forms.py
│   │   └── templatetags/
│   │
│   ├── services/            # Services métier
│   │   ├── alerting/
│   │   ├── chatops/
│   │   ├── notifications/
│   │   └── orchestrator.py
│   │
│   ├── templates/           # Templates Django
│   ├── tests/               # Tests
│   └── manage.py
│
├── docker/                    # Configuration Docker
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── docs/                      # Documentation
│
├── requirements.txt           # Dépendances production
├── requirements-dev.txt       # Dépendances développement
├── pyproject.toml            # Configuration outils Python
└── README.md
```

---

## Standards de Code

### Style Python

Nous utilisons **Ruff** pour le linting et le formatage :

```bash
# Vérifier
ruff check app/

# Corriger automatiquement
ruff check app/ --fix

# Formater
ruff format app/
```

### Configuration Ruff

```toml
# pyproject.toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # Pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
]

[tool.ruff.lint.isort]
known-first-party = ["core", "api", "dashboard", "services"]
```

### Conventions de Nommage

| Type | Convention | Exemple |
|------|------------|---------|
| Classes | PascalCase | `IncidentOrchestrator` |
| Fonctions | snake_case | `create_incident()` |
| Constantes | UPPER_CASE | `DEFAULT_SEVERITY` |
| Variables | snake_case | `incident_count` |
| Fichiers | snake_case | `notification_router.py` |

### Type Hints

Utiliser les type hints Python 3.11+ :

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Incident


def process_incident(incident_id: str) -> Incident | None:
    """
    Process an incident by ID.
    
    Args:
        incident_id: UUID of the incident.
        
    Returns:
        The processed Incident or None if not found.
    """
    ...
```

### Docstrings

Format Google :

```python
def calculate_mttr(incident: Incident) -> timedelta | None:
    """
    Calculate Mean Time To Resolve for an incident.
    
    Args:
        incident: The incident to calculate MTTR for.
        
    Returns:
        The time delta between creation and resolution,
        or None if the incident is not resolved.
        
    Raises:
        ValueError: If the incident has invalid timestamps.
        
    Example:
        >>> mttr = calculate_mttr(incident)
        >>> print(f"MTTR: {mttr.total_seconds() / 60} minutes")
    """
    if not incident.resolved_at:
        return None
    return incident.resolved_at - incident.created_at
```

---

## Tests

### Framework

- **pytest** pour les tests
- **pytest-django** pour l'intégration Django
- **pytest-cov** pour la couverture

### Lancer les Tests

```bash
cd app

# Tous les tests
pytest

# Avec couverture
pytest --cov=. --cov-report=html

# Tests spécifiques
pytest tests/test_orchestrator.py
pytest tests/test_api.py::TestIncidentAPI::test_create_incident

# Tests par marqueur
pytest -m "slow"
pytest -m "not slow"
```

### Structure des Tests

```
app/tests/
├── conftest.py              # Fixtures partagées
├── factories.py             # Factory Boy factories
├── test_api/
│   ├── test_incidents.py
│   ├── test_webhooks.py
│   └── test_auth.py
├── test_services/
│   ├── test_orchestrator.py
│   ├── test_notifications.py
│   └── test_escalation.py
├── test_models/
│   ├── test_incident.py
│   └── test_service.py
└── test_integration/
    └── test_full_workflow.py
```

### Exemple de Test

```python
# tests/test_services/test_orchestrator.py
import pytest
from unittest.mock import patch, MagicMock

from services.orchestrator import IncidentOrchestrator
from tests.factories import ServiceFactory, UserFactory


@pytest.fixture
def orchestrator():
    return IncidentOrchestrator()


@pytest.fixture
def service(db):
    return ServiceFactory(name="test-service")


@pytest.fixture
def user(db):
    return UserFactory()


class TestIncidentOrchestrator:
    """Tests for IncidentOrchestrator service."""

    def test_create_incident_success(self, orchestrator, service, user):
        """Test successful incident creation."""
        data = {
            "title": "Test Incident",
            "description": "Test description",
            "service": service.id,
            "severity": "SEV3_MEDIUM",
        }
        
        incident = orchestrator.create_incident(data, user=user)
        
        assert incident is not None
        assert incident.title == "Test Incident"
        assert incident.service == service
        assert incident.lead == user
        assert incident.status == "TRIGGERED"

    def test_create_incident_triggers_orchestration(self, orchestrator, service, user):
        """Test that orchestration task is triggered."""
        with patch("services.orchestrator.orchestrate_incident_task.delay") as mock_task:
            data = {
                "title": "Test Incident",
                "service": service.id,
            }
            
            incident = orchestrator.create_incident(data, user=user)
            
            mock_task.assert_called_once_with(str(incident.id))

    def test_deduplicate_check_finds_existing(self, orchestrator, service, db):
        """Test deduplication finds existing open incident."""
        # Create existing incident
        from tests.factories import IncidentFactory
        existing = IncidentFactory(
            service=service,
            status="TRIGGERED",
        )
        
        result = orchestrator.deduplicate_check(service)
        
        assert result == existing

    @pytest.mark.slow
    def test_full_orchestration_workflow(self, orchestrator, service, user):
        """Integration test for full orchestration workflow."""
        # This test is marked slow and may be skipped in CI
        ...
```

### Factories

```python
# tests/factories.py
import factory
from factory.django import DjangoModelFactory

from core.models import Incident, Service, Team
from django.contrib.auth import get_user_model


class UserFactory(DjangoModelFactory):
    class Meta:
        model = get_user_model()
    
    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")


class TeamFactory(DjangoModelFactory):
    class Meta:
        model = Team
    
    name = factory.Sequence(lambda n: f"Team {n}")
    slack_channel_id = factory.Sequence(lambda n: f"C{n:010d}")


class ServiceFactory(DjangoModelFactory):
    class Meta:
        model = Service
    
    name = factory.Sequence(lambda n: f"service-{n}")
    owner_team = factory.SubFactory(TeamFactory)
    criticality = "TIER_2"


class IncidentFactory(DjangoModelFactory):
    class Meta:
        model = Incident
    
    title = factory.Sequence(lambda n: f"Incident {n}")
    service = factory.SubFactory(ServiceFactory)
    severity = "SEV3_MEDIUM"
    status = "TRIGGERED"
```

### Couverture Minimum

- **Global** : 80%
- **Services critiques** : 90%
- **API** : 85%

---

## Git Workflow

### Branches

| Branche | Description |
|---------|-------------|
| `main` | Production, stable |
| `develop` | Développement, intégration |
| `feature/*` | Nouvelles fonctionnalités |
| `bugfix/*` | Corrections de bugs |
| `hotfix/*` | Corrections urgentes prod |
| `release/*` | Préparation release |

### Workflow

```
main ─────────────────────────────────────────────►
       │                                    ▲
       │                                    │
       ├─── develop ────────────────────────┼──────►
       │       │                ▲           │
       │       │                │           │
       │       ├── feature/xyz ─┘           │
       │       │                            │
       │       ├── bugfix/abc ──────────────┘
       │       │
       │       └── release/1.2.0
       │
       └── hotfix/critical-fix ─────────────────────►
```

### Commits Conventionnels

Format : `type(scope): description`

| Type | Description |
|------|-------------|
| `feat` | Nouvelle fonctionnalité |
| `fix` | Correction de bug |
| `docs` | Documentation |
| `style` | Formatage (pas de changement de code) |
| `refactor` | Refactoring |
| `test` | Ajout/modification de tests |
| `chore` | Maintenance, dépendances |

Exemples :

```bash
feat(api): add incident comments endpoint
fix(notifications): fix Slack message formatting
docs(readme): update installation instructions
refactor(orchestrator): extract notification logic
test(api): add tests for webhook endpoints
chore(deps): update Django to 5.2.10
```

---

## Pull Requests

### Checklist PR

Avant de soumettre une PR :

- [ ] Tests ajoutés/mis à jour
- [ ] Documentation mise à jour
- [ ] `ruff check` passe sans erreur
- [ ] `pytest` passe
- [ ] Commits atomiques avec messages clairs
- [ ] Branche à jour avec `develop`

### Template PR

```markdown
## Description

Brève description des changements.

## Type de changement

- [ ] Bug fix
- [ ] Nouvelle fonctionnalité
- [ ] Breaking change
- [ ] Documentation

## Comment tester

1. Étape 1
2. Étape 2
3. Résultat attendu

## Checklist

- [ ] Mon code suit les standards du projet
- [ ] J'ai ajouté des tests
- [ ] La documentation est à jour
- [ ] Les tests passent localement
```

### Review Process

1. **Auto-review** : Vérifiez votre propre PR
2. **CI** : Attendez que les checks passent
3. **Review** : 1 approbation requise
4. **Merge** : Squash and merge

---

## Documentation

### Où Documenter

| Type | Emplacement |
|------|-------------|
| API | Docstrings + OpenAPI |
| Fonctionnalités | `docs/*.md` |
| Architecture | `docs/` |
| README | Racine du projet |
| Code | Docstrings, commentaires |

### Style Documentation

- Markdown pour tous les docs
- Diagrammes ASCII ou Mermaid
- Exemples de code fonctionnels
- Français pour la documentation utilisateur

### Mise à Jour

Toute PR incluant des changements fonctionnels doit mettre à jour la documentation correspondante.

---

## Releases

### Versioning

Semantic Versioning : `MAJOR.MINOR.PATCH`

- **MAJOR** : Breaking changes
- **MINOR** : Nouvelles fonctionnalités (rétro-compatible)
- **PATCH** : Bug fixes

### Process de Release

1. Créer branche `release/X.Y.Z`
2. Mettre à jour `CHANGELOG.md`
3. Mettre à jour la version dans `pyproject.toml`
4. PR vers `main`
5. Tag après merge
6. GitHub Actions publie automatiquement

### Changelog

Format Keep a Changelog :

```markdown
## [1.2.0] - 2026-02-05

### Added
- Support ntfy.sh notifications (#123)
- Runbook execution tracking (#125)

### Changed
- Improved escalation logic (#124)

### Fixed
- Slack message formatting bug (#126)

### Deprecated
- Old webhook format (will be removed in 2.0)
```

---

## Contact

- **Issues** : GitHub Issues
- **Discussions** : GitHub Discussions
- **Slack** : #imas-dev (interne)

---

*Merci de contribuer à IMAS Manager !* 🚀
