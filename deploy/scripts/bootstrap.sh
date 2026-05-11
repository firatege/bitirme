#!/usr/bin/env bash
# One-shot bootstrap for the bitirme namespace:
#   - creates namespace
#   - prompts for DB password and writes the bitirme-postgres Secret
#   - bakes grafana provisioning files into ConfigMaps (referenced by values/grafana.yaml)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KUBECONTEXT="${KUBECONTEXT:-umceko}"
NAMESPACE="${NAMESPACE:-bitirme}"

K() { kubectl --context "$KUBECONTEXT" "$@"; }
KN() { K -n "$NAMESPACE" "$@"; }

echo ">> ensuring namespace '$NAMESPACE'"
K get ns "$NAMESPACE" >/dev/null 2>&1 || K create ns "$NAMESPACE"

if ! KN get secret bitirme-postgres >/dev/null 2>&1; then
    DB_PASS="${DB_PASSWORD:-}"
    if [ -z "$DB_PASS" ]; then
        read -r -s -p "Postgres password for user 'bitirme': " DB_PASS
        echo
    fi
    echo ">> creating bitirme-postgres secret"
    KN create secret generic bitirme-postgres \
        --from-literal=username=bitirme \
        --from-literal=password="$DB_PASS" \
        --from-literal=database=bitirme
else
    echo ">> bitirme-postgres secret already exists — skipping"
fi

if ! KN get secret regcred >/dev/null 2>&1; then
    HUB_USER="${HUB_USER:-bitirme}"
    HUB_PASS="${HUB_PASSWORD:-}"
    if [ -z "$HUB_PASS" ]; then
        read -r -s -p "hub.umceko.com password for user '$HUB_USER': " HUB_PASS
        echo
    fi
    echo ">> creating regcred pull secret"
    KN create secret docker-registry regcred \
        --docker-server=hub.umceko.com \
        --docker-username="$HUB_USER" \
        --docker-password="$HUB_PASS"
else
    echo ">> regcred secret already exists — skipping"
fi

echo ">> applying grafana provisioning configmaps"
KN create configmap bitirme-grafana-datasources \
    --from-file="$ROOT/deploy/grafana/provisioning/datasources" \
    --dry-run=client -o yaml | KN apply -f -

KN create configmap bitirme-grafana-dashboards-config \
    --from-file="$ROOT/deploy/grafana/provisioning/dashboards" \
    --dry-run=client -o yaml | KN apply -f -

KN create configmap bitirme-grafana-dashboards \
    --from-file="$ROOT/deploy/grafana/dashboards" \
    --dry-run=client -o yaml | KN apply -f -

echo ">> bootstrap complete"
