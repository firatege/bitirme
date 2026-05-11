#!/usr/bin/env bash
# Build → push → helm upgrade for a single service.
# Mirrors tb-monorepo/scripts/deploy.sh, single-environment edition.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

SERVICE="${1:-}"
shift || true
EXTRA_HELM_FLAGS=()
BUILD_ONLY=0
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --build-only) BUILD_ONLY=1 ;;
        --dry-run)    DRY_RUN=1; EXTRA_HELM_FLAGS+=("--dry-run") ;;
        *)            EXTRA_HELM_FLAGS+=("$arg") ;;
    esac
done

if [ -z "$SERVICE" ]; then
    echo "usage: $0 <service> [--build-only|--dry-run]" >&2
    echo "services: api controller dashboard postgres grafana" >&2
    exit 1
fi

REGISTRY="${REGISTRY:-hub.umceko.com/bitirme}"
KUBECONTEXT="${KUBECONTEXT:-umceko}"
NAMESPACE="${NAMESPACE:-bitirme}"
DOMAIN="${DOMAIN:-bitirme.umceko.com}"

CHART_DIR="$ROOT/deploy/helm"
VALUES_FILE="$CHART_DIR/values/$SERVICE.yaml"

if [ ! -f "$VALUES_FILE" ]; then
    echo "error: no values file for service '$SERVICE' (expected $VALUES_FILE)" >&2
    exit 1
fi

GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo dev)"
# Append a -dirty<ts> suffix when there are uncommitted changes so k8s rolls the deployment
# instead of reusing the same tag (which IfNotPresent would happily cache).
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    GIT_SHA="${GIT_SHA}-dirty$(date +%s)"
fi
TAG="${IMAGE_TAG:-$GIT_SHA}"
IMAGE_REPO="$REGISTRY/$SERVICE"
IMAGE="$IMAGE_REPO:$TAG"

# Map service → Dockerfile (postgres/grafana use upstream images and skip build/push).
case "$SERVICE" in
    api)        DOCKERFILE="$ROOT/deploy/docker/Dockerfile.api" ;;
    controller) DOCKERFILE="$ROOT/deploy/docker/Dockerfile.controller" ;;
    dashboard)  DOCKERFILE="$ROOT/deploy/docker/Dockerfile.dashboard" ;;
    postgres|grafana) DOCKERFILE="" ;;
    *) echo "error: unknown service '$SERVICE'" >&2; exit 1 ;;
esac

if [ -n "$DOCKERFILE" ]; then
    echo ">> building $IMAGE"
    BUILD_ARGS=()
    if [ "$SERVICE" = "dashboard" ]; then
        BUILD_ARGS+=(--build-arg "VITE_API_BASE_URL=https://$DOMAIN/api")
        BUILD_ARGS+=(--build-arg "VITE_GRAFANA_URL=https://$DOMAIN/grafana")
    fi
    docker build "$ROOT" -f "$DOCKERFILE" -t "$IMAGE" "${BUILD_ARGS[@]}"

    if [ "$BUILD_ONLY" -eq 0 ]; then
        echo ">> pushing $IMAGE"
        docker push "$IMAGE"
    fi
fi

if [ "$BUILD_ONLY" -eq 1 ]; then
    echo ">> build-only complete: $IMAGE"
    exit 0
fi

echo ">> helm upgrade --install $SERVICE (ns=$NAMESPACE, ctx=$KUBECONTEXT)"
HELM_SET=(--set "ingress.host=$DOMAIN")
# Only override image for services we actually build — postgres/grafana keep upstream images.
if [ -n "$DOCKERFILE" ]; then
    HELM_SET+=(--set "app.image.repository=$IMAGE_REPO" --set "app.image.tag=$TAG")
fi
helm --kube-context "$KUBECONTEXT" upgrade --install "$SERVICE" "$CHART_DIR" \
    -f "$VALUES_FILE" \
    -n "$NAMESPACE" \
    --create-namespace \
    "${HELM_SET[@]}" \
    "${EXTRA_HELM_FLAGS[@]}"

if [ "$DRY_RUN" -eq 0 ]; then
    echo ">> done: $SERVICE @ $TAG"
fi
