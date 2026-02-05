# Guide d'Installation & Déploiement

> Guide complet pour installer et déployer IMAS Manager

---

## 📋 Table des Matières

1. [Prérequis](#prérequis)
2. [Installation Locale (Développement)](#installation-locale-développement)
3. [Déploiement Docker/Podman](#déploiement-dockerpodman)
4. [Déploiement Kubernetes](#déploiement-kubernetes)
5. [Variables d'Environnement](#variables-denvironnement)
6. [Configuration SSL/TLS](#configuration-ssltls)
7. [Reverse Proxy (Nginx)](#reverse-proxy-nginx)
8. [Monitoring & Health Checks](#monitoring--health-checks)

---

## Prérequis

### Développement Local

| Composant | Version Minimum | Recommandé |
|-----------|-----------------|------------|
| Python | 3.11 | 3.12 |
| PostgreSQL | 14 | 16 |
| Redis | 6 | 7 |
| Node.js (optionnel) | 18 | 20 |

### Production (Docker)

| Composant | Version |
|-----------|---------|
| Docker / Podman | 24+ / 4+ |
| Docker Compose / Podman Compose | 2.20+ |

### Production (Kubernetes)

| Composant | Version |
|-----------|---------|
| Kubernetes | 1.28+ |
| Helm | 3.12+ |

---

## Installation Locale (Développement)

### 1. Cloner le Dépôt

```bash
git clone https://github.com/SeeMyPing/imas-manager.git
cd imas-manager
```

### 2. Créer l'Environnement Virtuel

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# ou
.venv\Scripts\activate     # Windows
```

### 3. Installer les Dépendances

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Outils de développement
```

### 4. Configurer les Variables d'Environnement

```bash
cd app
cp .env.example .env
```

Éditer `.env` :

```bash
# Django
DEBUG=True
SECRET_KEY=your-secret-key-for-development-only
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (SQLite pour dev)
DATABASE_URL=sqlite:///db.sqlite3

# Ou PostgreSQL
# DATABASE_URL=postgres://user:pass@localhost:5432/imas_db

# Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### 5. Démarrer les Services Requis

#### Option A : Redis local

```bash
# macOS
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis
```

#### Option B : Redis via Docker

```bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

### 6. Appliquer les Migrations

```bash
cd app
python manage.py migrate
```

### 7. Créer un Superutilisateur

```bash
python manage.py createsuperuser
```

### 8. Démarrer le Serveur de Développement

```bash
# Terminal 1 : Django
python manage.py runserver

# Terminal 2 : Celery Worker
celery -A config worker --loglevel=info

# Terminal 3 (optionnel) : Celery Beat
celery -A config beat --loglevel=info
```

### 9. Accéder à l'Application

- **Dashboard** : http://localhost:8000/dashboard/
- **Admin** : http://localhost:8000/admin/
- **API Docs** : http://localhost:8000/api/docs/

---

## Déploiement Docker/Podman

### 1. Structure du Projet

```
imas-manager/
├── app/                    # Code Django
├── docker/
│   ├── Dockerfile         # Image de l'application
│   ├── docker-compose.yml # Orchestration
│   └── .env.example       # Template variables
```

### 2. Configuration

```bash
cd docker
cp .env.example .env
```

Éditer `.env` :

```bash
# Django
DEBUG=False
SECRET_KEY=your-super-secret-production-key-change-me
ALLOWED_HOSTS=imas.example.com,localhost

# PostgreSQL
POSTGRES_DB=imas_db
POSTGRES_USER=imas_user
POSTGRES_PASSWORD=super-secure-password-change-me

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

### 3. Build et Démarrage

```bash
# Docker
docker compose up --build -d

# Podman
podman compose up --build -d
```

### 4. Créer le Superutilisateur

```bash
# Docker
docker exec -it imas_web python manage.py createsuperuser

# Podman
podman exec -it imas_web python manage.py createsuperuser
```

### 5. Vérifier les Services

```bash
# Docker
docker ps
docker logs imas_web

# Podman
podman ps
podman logs imas_web
```

### 6. Services Déployés

| Service | Container | Port |
|---------|-----------|------|
| Django + Gunicorn | imas_web | 8000 |
| Celery Worker | imas_worker | - |
| Celery Beat | imas_beat | - |
| PostgreSQL | imas_postgres | 5432 |
| Redis | imas_redis | 6379 |

### 7. Commandes Utiles

```bash
# Voir les logs
docker compose logs -f

# Redémarrer un service
docker compose restart web

# Arrêter tout
docker compose down

# Arrêter et supprimer les volumes
docker compose down -v
```

---

## Déploiement Kubernetes

### 1. Prérequis

- Cluster Kubernetes fonctionnel
- `kubectl` configuré
- Helm 3 installé
- Secret pour les credentials

### 2. Créer le Namespace

```bash
kubectl create namespace imas
```

### 3. Créer les Secrets

```bash
kubectl create secret generic imas-secrets \
  --namespace imas \
  --from-literal=SECRET_KEY='your-production-secret-key' \
  --from-literal=POSTGRES_PASSWORD='db-password' \
  --from-literal=DATABASE_URL='postgres://imas:db-password@postgres:5432/imas'
```

### 4. Déployer PostgreSQL (via Helm)

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install postgres bitnami/postgresql \
  --namespace imas \
  --set auth.username=imas \
  --set auth.password=db-password \
  --set auth.database=imas \
  --set primary.persistence.size=10Gi
```

### 5. Déployer Redis (via Helm)

```bash
helm install redis bitnami/redis \
  --namespace imas \
  --set auth.enabled=false \
  --set replica.replicaCount=0
```

### 6. Manifestes Kubernetes

#### Deployment (web)

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: imas-web
  namespace: imas
spec:
  replicas: 3
  selector:
    matchLabels:
      app: imas-web
  template:
    metadata:
      labels:
        app: imas-web
    spec:
      containers:
      - name: web
        image: ghcr.io/seemyping/imas-manager:latest
        ports:
        - containerPort: 8000
        envFrom:
        - secretRef:
            name: imas-secrets
        env:
        - name: CELERY_BROKER_URL
          value: redis://redis-master:6379/0
        livenessProbe:
          httpGet:
            path: /api/health/
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/health/
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

#### Service

```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: imas-web
  namespace: imas
spec:
  selector:
    app: imas-web
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP
```

#### Ingress

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: imas-ingress
  namespace: imas
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - imas.example.com
    secretName: imas-tls
  rules:
  - host: imas.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: imas-web
            port:
              number: 80
```

### 7. Appliquer les Manifestes

```bash
kubectl apply -f k8s/
```

---

## Variables d'Environnement

### Variables Obligatoires

| Variable | Description | Exemple |
|----------|-------------|---------|
| `SECRET_KEY` | Clé secrète Django (min 50 chars) | `django-insecure-xxx...` |
| `DATABASE_URL` | URL de connexion PostgreSQL | `postgres://user:pass@host:5432/db` |
| `CELERY_BROKER_URL` | URL Redis pour Celery | `redis://redis:6379/0` |

### Variables Optionnelles

| Variable | Description | Défaut |
|----------|-------------|--------|
| `DEBUG` | Mode debug Django | `False` |
| `ALLOWED_HOSTS` | Hosts autorisés | `localhost` |
| `CELERY_RESULT_BACKEND` | Backend résultats Celery | `redis://redis:6379/0` |
| `LOG_LEVEL` | Niveau de log | `INFO` |
| `STATIC_URL` | URL des fichiers statiques | `/static/` |

### Variables Email

| Variable | Description |
|----------|-------------|
| `EMAIL_HOST` | Serveur SMTP |
| `EMAIL_PORT` | Port SMTP |
| `EMAIL_HOST_USER` | Utilisateur SMTP |
| `EMAIL_HOST_PASSWORD` | Mot de passe SMTP |
| `EMAIL_USE_TLS` | Utiliser TLS |
| `DEFAULT_FROM_EMAIL` | Email expéditeur |

### Variables Intégrations

| Variable | Description |
|----------|-------------|
| `SLACK_BOT_TOKEN` | Token bot Slack |
| `GOOGLE_DRIVE_CREDENTIALS` | Credentials Service Account (base64) |

---

## Configuration SSL/TLS

### Avec Nginx (Recommandé)

```nginx
server {
    listen 443 ssl http2;
    server_name imas.example.com;
    
    ssl_certificate /etc/letsencrypt/live/imas.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/imas.example.com/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Avec Traefik (Docker)

```yaml
# docker-compose.yml
services:
  traefik:
    image: traefik:v2.10
    command:
      - "--providers.docker=true"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.le.acme.tlschallenge=true"
      - "--certificatesresolvers.le.acme.email=admin@example.com"
    ports:
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock

  web:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.imas.rule=Host(`imas.example.com`)"
      - "traefik.http.routers.imas.tls.certresolver=le"
```

---

## Reverse Proxy (Nginx)

### Configuration Complète

```nginx
upstream imas_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name imas.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name imas.example.com;
    
    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/imas.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/imas.example.com/privkey.pem;
    
    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    # Gzip
    gzip on;
    gzip_types text/plain application/json application/javascript text/css;
    
    # Static files
    location /static/ {
        alias /var/www/imas/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    
    # Media files
    location /media/ {
        alias /var/www/imas/media/;
        expires 7d;
    }
    
    # API & Dashboard
    location / {
        proxy_pass http://imas_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Health check (no auth, no logs)
    location /api/health/ {
        proxy_pass http://imas_backend;
        access_log off;
    }
}
```

---

## Monitoring & Health Checks

### Endpoints de Santé

| Endpoint | Description | Auth |
|----------|-------------|------|
| `GET /api/health/` | Health check basique | Non |
| `GET /api/v1/health/` | Health check API | Non |

### Exemple de Réponse

```json
{
  "status": "healthy",
  "service": "imas-manager",
  "version": "1.0.0"
}
```

### Prometheus Metrics

Si configuré, les métriques sont disponibles sur `/metrics/`.

### Alertes Recommandées

```yaml
# prometheus/alerts.yml
groups:
- name: imas
  rules:
  - alert: IMASDown
    expr: up{job="imas"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "IMAS Manager is down"
      
  - alert: IMASHighLatency
    expr: http_request_duration_seconds{job="imas"} > 1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "IMAS Manager high latency"
```

---

*Documentation générée le 5 février 2026 - IMAS Manager v1.0*
