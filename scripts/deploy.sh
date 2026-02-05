#!/bin/bash
# =============================================================================
# IMAS Manager - Deployment Script
# Usage: ./deploy.sh [staging|production] [version]
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="${SCRIPT_DIR}/../k8s"
DOCKER_DIR="${SCRIPT_DIR}/../docker"
IMAGE_NAME="ghcr.io/seemyping/imas-manager"

# Default values
ENVIRONMENT="${1:-staging}"
VERSION="${2:-latest}"

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
    echo -e "${RED}Error: Invalid environment. Use 'staging' or 'production'${NC}"
    exit 1
fi

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local missing_tools=()
    
    for tool in kubectl kustomize docker; do
        if ! command -v "$tool" &> /dev/null; then
            missing_tools+=("$tool")
        fi
    done
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        exit 1
    fi
    
    # Check kubectl context
    local context
    context=$(kubectl config current-context)
    log_warning "Current kubectl context: $context"
    
    if [[ "$ENVIRONMENT" == "production" ]]; then
        read -p "You are deploying to PRODUCTION. Continue? (yes/no): " confirm
        if [[ "$confirm" != "yes" ]]; then
            log_info "Deployment cancelled."
            exit 0
        fi
    fi
    
    log_success "Prerequisites check passed"
}

# Build Docker image
build_image() {
    log_info "Building Docker image: ${IMAGE_NAME}:${VERSION}"
    
    cd "${DOCKER_DIR}/.."
    
    docker build \
        --target production \
        --tag "${IMAGE_NAME}:${VERSION}" \
        --tag "${IMAGE_NAME}:${ENVIRONMENT}" \
        --build-arg BUILDKIT_INLINE_CACHE=1 \
        --cache-from "${IMAGE_NAME}:${ENVIRONMENT}" \
        --file docker/Dockerfile \
        .
    
    log_success "Docker image built successfully"
}

# Push Docker image
push_image() {
    log_info "Pushing Docker image to registry..."
    
    docker push "${IMAGE_NAME}:${VERSION}"
    docker push "${IMAGE_NAME}:${ENVIRONMENT}"
    
    log_success "Docker image pushed successfully"
}

# Deploy to Kubernetes
deploy_k8s() {
    log_info "Deploying to Kubernetes ($ENVIRONMENT)..."
    
    local overlay_dir="${K8S_DIR}/overlays/${ENVIRONMENT}"
    
    if [ ! -d "$overlay_dir" ]; then
        log_error "Overlay directory not found: $overlay_dir"
        exit 1
    fi
    
    # Generate manifests and apply
    log_info "Applying Kustomize manifests..."
    
    # Dry run first
    kubectl kustomize "$overlay_dir" | kubectl apply --dry-run=client -f -
    
    # Apply for real
    kubectl kustomize "$overlay_dir" | kubectl apply -f -
    
    log_success "Kubernetes resources applied"
}

# Wait for deployment
wait_for_deployment() {
    log_info "Waiting for deployment to be ready..."
    
    local namespace="imas-${ENVIRONMENT}"
    local deployment_name="${ENVIRONMENT:0:4}-imas-web"  # staging- or prod- prefix
    
    kubectl rollout status deployment/"$deployment_name" \
        -n "$namespace" \
        --timeout=5m
    
    log_success "Deployment is ready"
}

# Run health checks
health_check() {
    log_info "Running health checks..."
    
    local namespace="imas-${ENVIRONMENT}"
    
    # Get pod status
    kubectl get pods -n "$namespace" -l app.kubernetes.io/name=imas-manager
    
    # Check if pods are ready
    local ready_pods
    ready_pods=$(kubectl get pods -n "$namespace" \
        -l app.kubernetes.io/name=imas-manager \
        -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}' | \
        grep -c "True" || echo "0")
    
    if [ "$ready_pods" -gt 0 ]; then
        log_success "Health check passed: $ready_pods pods are ready"
    else
        log_error "Health check failed: No pods are ready"
        exit 1
    fi
}

# Print deployment info
print_info() {
    echo ""
    echo -e "${GREEN}=========================================${NC}"
    echo -e "${GREEN}  Deployment Summary${NC}"
    echo -e "${GREEN}=========================================${NC}"
    echo -e "Environment: ${BLUE}${ENVIRONMENT}${NC}"
    echo -e "Version:     ${BLUE}${VERSION}${NC}"
    echo -e "Image:       ${BLUE}${IMAGE_NAME}:${VERSION}${NC}"
    echo ""
    
    local namespace="imas-${ENVIRONMENT}"
    log_info "Resources in namespace $namespace:"
    kubectl get all -n "$namespace" -l app.kubernetes.io/name=imas-manager
}

# Main execution
main() {
    echo ""
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}  IMAS Manager Deployment${NC}"
    echo -e "${BLUE}=========================================${NC}"
    echo -e "Environment: ${YELLOW}${ENVIRONMENT}${NC}"
    echo -e "Version:     ${YELLOW}${VERSION}${NC}"
    echo ""
    
    check_prerequisites
    build_image
    push_image
    deploy_k8s
    wait_for_deployment
    health_check
    print_info
    
    echo ""
    log_success "Deployment completed successfully! 🚀"
}

# Run main function
main "$@"
