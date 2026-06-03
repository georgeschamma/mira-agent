# Azure Container Apps Smoke Deploy

This app deploys as one Docker image: FastAPI serves the API and the built React/Vite bundle.
Use Azure Container Apps runtime env vars for configuration. Do not commit keys.

## Prerequisites

```bash
az login
az account show
az extension add --name containerapp --upgrade
```

Supabase must be reachable from Azure. A local `127.0.0.1` Supabase URL will not work for the
Azure smoke test.

## Variables

```bash
export RG=mira-phase-2-rg
export LOCATION=eastus
export ACR_NAME=miraphase2acr
export ACA_ENV=mira-phase-2-env
export APP_NAME=mira-agent
export IMAGE="$ACR_NAME.azurecr.io/mira-agent:phase-2"
export SUPABASE_URL="https://replace-with-project.supabase.co"
```

## Build and Push

```bash
az group create --name "$RG" --location "$LOCATION"
az acr create --resource-group "$RG" --name "$ACR_NAME" --sku Basic
az acr login --name "$ACR_NAME"

docker build -t "$IMAGE" .
docker push "$IMAGE"
```

## Create Environment

```bash
az containerapp env create \
  --name "$ACA_ENV" \
  --resource-group "$RG" \
  --location "$LOCATION"
```

## Create App With Secrets

Set secret values in the command line or from your shell. Do not print them in logs.

```bash
az containerapp create \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --environment "$ACA_ENV" \
  --image "$IMAGE" \
  --target-port 8123 \
  --ingress external \
  --registry-server "$ACR_NAME.azurecr.io" \
  --secrets \
    supabase-anon-key="<SUPABASE_ANON_KEY>" \
    llm-api-key="<LLM_API_KEY>" \
    exa-api-key="<EXA_API_KEY>" \
  --env-vars \
    APP_ENV=azure \
    API_PORT=8123 \
    CORS_ORIGINS="https://$APP_NAME.<replace-with-aca-domain>" \
    SUPABASE_URL="$SUPABASE_URL" \
    SUPABASE_ANON_KEY=secretref:supabase-anon-key \
    LLM_PROVIDER=openai-compatible \
    LLM_MODEL=gpt-5.5 \
    LLM_BASE_URL=https://api.freemodel.dev/v1 \
    LLM_API_KEY=secretref:llm-api-key \
    EXA_API_KEY=secretref:exa-api-key \
    EXA_NUM_RESULTS=5
```

`SUPABASE_SERVICE_ROLE_KEY` is not used on request paths. Keep it out of the running app unless
you need one-off seed/admin commands, and use `secretref:` if you add it as an env var.

## Update Existing App

```bash
az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --image "$IMAGE" \
  --set-env-vars \
    SUPABASE_URL="$SUPABASE_URL" \
    SUPABASE_ANON_KEY=secretref:supabase-anon-key \
    LLM_API_KEY=secretref:llm-api-key \
    EXA_API_KEY=secretref:exa-api-key
```

## Smoke Checks

```bash
export APP_URL="https://$(az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --query properties.configuration.ingress.fqdn \
  -o tsv)"

curl -fsS "$APP_URL/health"
curl -fsS "$APP_URL/health/db"
curl -fsS "$APP_URL/api/config"
```

Then open `$APP_URL` in a clean browser and verify:

- Login works for the seeded Analyst user.
- Submit a brief and receive a sourced report.
- Audit trace shows `router`, `research`, and `content` in order.
- Markdown export downloads a non-empty report.
- Analyst approval is rejected or hidden.
- Admin can approve or reject a pending high-impact recommendation.
