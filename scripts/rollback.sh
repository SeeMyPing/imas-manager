#!/bin/bash
# =============================================================================
# IMAS Manager - Rollback Script
# Usage: ./rollback.sh [staging|production] [revision]
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
ENVIRONMENT="${1:-staging}"
REVISION="${2:-}"

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

# Set namespace based on environment
get_namespace() {
    echo "imas-${ENVIRONMENT}"
}

# Get deployment prefix based on environment
get_prefix() {
    if [[ "$ENVIRONMENT" == "staging" ]]; then
        echo "staging-"
    else
        echo "prod-"
    fi
}

# Show rollout history
show_history() {
    local namespace
    local prefix
    namespace=$(get_namespace)
    prefix=$(get_prefix)
    
    log_info "Rollout history for ${ENVIRONMENT}:"
    echo ""
    
    for deployment in imas-web imas-worker imas-beat; do
        local full_name="${prefix}${deployment}"
        echo -e "${BLUE}=== ${full_name} ===${NC}"
        kubectl rollout history deployment/"$full_name" -n "$namespace" 2>/dev/null || \
            echo "Deployment not found"
        echo ""
    done
}

# Perform rollback
do_rollback() {
    local namespace
    local prefix
    namespace=$(get_namespace)
    prefix=$(get_prefix)
    
    if [[ "$ENVIRONMENT" == "production" ]]; then
        log_warning "You are about to rollback PRODUCTION!"
        read -p "Are you sure? (yes/no): " confirm
        if [[ "$confirm" != "yes" ]]; then
            log_info "Rollback cancelled."
            exit 0
        fi
    fi
    
    local rollback_cmd="rollout undo"
    if [[ -n "$REVISION" ]]; then
        rollback_cmd="rollout undo --to-revision=$REVISION"
    fi
    
    log_info "Rolling back deployments..."
    
    for deployment in imas-web imas-worker; do
        local full_name="${prefix}${deployment}"
        log_info "Rolling back $full_name..."
        kubectl $rollback_cmd deployment/"$full_name" -n "$namespace"
    done
    
    log_success "Rollback initiated"
}

# Wait for rollback to complete
wait_for_rollback() {
    local namespace
    local prefix
    namespace=$(get_namespace)
    prefix=$(get_prefix)
    
    log_info "Waiting for rollback to complete..."
    
    for deployment in imas-web imas-worker; do
        local full_name="${prefix}${deployment}"
        kubectl rollout status deployment/"$full_name" -n "$namespace" --timeout=5m
    done
    
    log_success "Rollback completed"
}

# Verify rollback
verify_rollback() {
    local namespace
    namespace=$(get_namespace)
    
    log_info "Verifying rollback..."
    
    kubectl get pods -n "$namespace" -l app.kubernetes.io/name=imas-manager
    
    # Check pod health
    sleep 10
    
    local ready_pods
    ready_pods=$(kubectl get pods -n "$namespace" \
        -l app.kubernetes.io/name=imas-manager \
        -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}' | \
        grep -c "True" || echo "0")
    
    if [ "$ready_pods" -gt 0 ]; then
        log_success "Rollback verified: $ready_pods pods are ready"
    else
        log_error "Rollback verification failed"
        exit 1
    fi
}

# Main
main() {
    echo ""
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}  IMAS Manager Rollback${NC}"
    echo -e "${BLUE}=========================================${NC}"
    echo -e "Environment: ${YELLOW}${ENVIRONMENT}${NC}"
    if [[ -n "$REVISION" ]]; then
        echo -e "Revision:    ${YELLOW}${REVISION}${NC}"
    else
        echo -e "Revision:    ${YELLOW}previous${NC}"
    fi
    echo ""
    
    show_history
    do_rollback
    wait_for_rollback
    verify_rollback
    
    echo ""
    log_success "Rollback completed successfully! ✅"
}

main "$@"
