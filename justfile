REGISTRY    := env_var_or_default("REGISTRY",    "hub.umceko.com/bitirme")
KUBECONTEXT := env_var_or_default("KUBECONTEXT", "umceko")
NAMESPACE   := env_var_or_default("NAMESPACE",   "bitirme")
DOMAIN      := env_var_or_default("DOMAIN",      "bitirme.umceko.com")

SERVICES := "api controller dashboard postgres grafana"

default:
    @just --list

# Show what would change without applying.
diff service:
    ./deploy/scripts/deploy.sh {{ service }} --dry-run

# Build + push + helm upgrade for a single service.
deploy service:
    ./deploy/scripts/deploy.sh {{ service }}

# Deploy everything in dependency order (postgres → api → controller → grafana → dashboard).
deploy-all:
    just deploy postgres
    just deploy api
    just deploy controller
    just deploy grafana
    just deploy dashboard

# Build the image for one service without pushing or deploying.
build service:
    ./deploy/scripts/deploy.sh {{ service }} --build-only

# kubectl shortcuts in the right context+namespace.
kubectl *args:
    kubectl --context {{ KUBECONTEXT }} -n {{ NAMESPACE }} {{ args }}

logs service:
    just kubectl logs -l app={{ service }} -f --tail=200

shell service:
    just kubectl exec -it deploy/{{ service }} -- /bin/sh

# Helm release management.
list:
    helm --kube-context {{ KUBECONTEXT }} -n {{ NAMESPACE }} list

uninstall service:
    helm --kube-context {{ KUBECONTEXT }} -n {{ NAMESPACE }} uninstall {{ service }}

# One-time bootstrap: create namespace + db secret + grafana provisioning configmaps.
bootstrap:
    ./deploy/scripts/bootstrap.sh

# Local docker login to hub.umceko.com — prompts for password (or reads $HUB_PASSWORD).
login user="bitirme":
    @if [ -n "${HUB_PASSWORD:-}" ]; then \
        echo "$HUB_PASSWORD" | docker login hub.umceko.com -u {{ user }} --password-stdin; \
    else \
        docker login hub.umceko.com -u {{ user }}; \
    fi

# One-shot DB seed (after postgres + controller are up).
seed:
    just kubectl exec -i deploy/controller -- controller migrate
    just kubectl exec -i deploy/controller -- controller seed \
        --panel /app/panel_sales_orders_stock.csv \
        --config /app/sku_config.csv
