# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Versioning Sémantique](https://semver.org/lang/fr/).

---

## [Unreleased]

### Added
- Documentation complète du projet
  - Guide d'installation et déploiement
  - Guide API complet
  - Guide d'administration
  - Runbooks et politiques d'escalade
  - Guide d'intégrations tierces
  - Guide des providers de notification

### Changed
- Amélioration de la configuration Celery Beat

### Fixed
- Correction du format de schedule Celery Beat (crontab)

---

## [1.0.0] - 2026-02-05

### Added

#### Core Incident Management
- Création et gestion des incidents
- Modèle de sévérité (SEV1 à SEV5)
- Statuts d'incident (Triggered, Acknowledged, Investigating, Identified, Monitoring, Resolved, Closed)
- Assignation automatique du lead incident
- Horodatage des changements d'état
- Timeline des événements

#### Services et Équipes
- Gestion des services avec niveaux de criticité (Tier 0-4)
- Gestion des équipes
- Plannings d'astreinte (on-call schedules)
- Rotations automatiques

#### Notifications
- Provider Slack avec création de canaux dédiés
- Provider Discord avec embeds riches
- Provider Email (SMTP)
- Provider OVH SMS
- Provider Webhook générique
- Provider ntfy.sh

#### Orchestration
- Orchestrateur d'incidents automatisé
- Déduplication intelligente des alertes
- Corrélation d'alertes
- Escalade automatique selon règles configurées

#### Runbooks
- Création et gestion de runbooks
- Association aux services
- Templates de runbooks
- Exécution trackée

#### API REST
- Authentification par Token
- CRUD complet incidents
- CRUD services
- CRUD équipes
- Webhooks entrants (Alertmanager, Datadog, Grafana, Sentry)
- Rate limiting configurable

#### Dashboard Web
- Interface de gestion des incidents
- Tableaux de bord temps réel
- Gestion des services
- Gestion des équipes
- Analytics et rapports

#### Intégrations
- Prometheus / Alertmanager
- Datadog
- Grafana
- Sentry
- Google Drive (post-mortems)
- SSO (SAML 2.0, OIDC)

#### Infrastructure
- Déploiement Docker / Podman
- Support Kubernetes (Helm chart)
- Celery pour tâches asynchrones
- Redis pour cache et broker
- PostgreSQL pour persistance

---

## Types de Changements

- **Added** : nouvelles fonctionnalités
- **Changed** : modifications de fonctionnalités existantes
- **Deprecated** : fonctionnalités bientôt supprimées
- **Removed** : fonctionnalités supprimées
- **Fixed** : corrections de bugs
- **Security** : corrections de vulnérabilités

---

## Notes de Migration

### Vers 1.0.0

Version initiale - pas de migration nécessaire.

```bash
# Installation initiale
cd app
python manage.py migrate
python manage.py createsuperuser
```

---

## Liens

- [Repository](https://github.com/SeeMyPing/imas-manager)
- [Issues](https://github.com/SeeMyPing/imas-manager/issues)
- [Documentation](./docs/)

[Unreleased]: https://github.com/SeeMyPing/imas-manager/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/SeeMyPing/imas-manager/releases/tag/v1.0.0
