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
export LOCATION=spaincentral
export ACR_NAME=miraphase2ocxng
export ACA_ENV=mira-phase-2-env
export APP_NAME=mira-agent-phase-2
export IMAGE_TAG="phase-3-$(git rev-parse --short HEAD)-amd64"
export IMAGE="$ACR_NAME.azurecr.io/mira-agent:$IMAGE_TAG"
export SUPABASE_URL="https://replace-with-project.supabase.co"
```

## Build and Push

The preferred path is the GitHub Actions workflow at
`.github/workflows/build-acr-image.yml`. It builds on an Ubuntu runner, targets `linux/amd64`, and
uses GitHub OIDC with the `mira-agent-github-acr-push` managed identity. That identity has only the
`AcrPush` role on `miraphase2ocxng`; no registry password or Azure client secret is stored in
GitHub.

Pushing `main` triggers the workflow. Use `workflow_dispatch` to build another selected branch. It
publishes:

```text
miraphase2ocxng.azurecr.io/mira-agent:phase-3-<short-git-sha>-amd64
```

Verify the tag before changing application or database permissions:

```bash
az acr repository show-tags \
  --name "$ACR_NAME" \
  --repository mira-agent \
  --orderby time_desc \
  --top 10 \
  -o tsv
```

For a local fallback:

```bash
az group create --name "$RG" --location "$LOCATION"
az acr create --resource-group "$RG" --name "$ACR_NAME" --sku Basic
az acr login --name "$ACR_NAME"

docker buildx build --platform linux/amd64 -t "$IMAGE" --push .
docker buildx imagetools inspect "$IMAGE"
```

Use the explicit `linux/amd64` target even when building on Apple Silicon. Azure Container Apps
cannot start an ARM-only image. This subscription also blocks ACR Tasks, so use local `buildx`
instead of `az acr build`.

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
    supabase-service-role-key="<SUPABASE_SERVICE_ROLE_KEY>" \
    llm-api-key="<LLM_API_KEY>" \
    exa-api-key="<EXA_API_KEY>" \
  --env-vars \
    APP_ENV=azure \
    API_PORT=8123 \
    CORS_ORIGINS="https://$APP_NAME.<replace-with-aca-domain>" \
    SUPABASE_URL="$SUPABASE_URL" \
    SUPABASE_ANON_KEY=secretref:supabase-anon-key \
    SUPABASE_SERVICE_ROLE_KEY=secretref:supabase-service-role-key \
    LLM_PROVIDER=openai-compatible \
    LLM_MODEL=gpt-5.5 \
    LLM_BASE_URL=https://api.freemodel.dev/v1 \
    LLM_API_KEY=secretref:llm-api-key \
    EXA_API_KEY=secretref:exa-api-key \
    EXA_NUM_RESULTS=5
```

`SUPABASE_SERVICE_ROLE_KEY` is required by FastAPI for trusted generated writes after user-JWT
authorization. Keep it backend-only, store it as an Azure `secretref:`, and never expose it through
`/api/config`, browser code, logs, or client requests.

## Update Existing App

```bash
az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --image "$IMAGE" \
  --set-env-vars \
    SUPABASE_URL="$SUPABASE_URL" \
    SUPABASE_ANON_KEY=secretref:supabase-anon-key \
    SUPABASE_SERVICE_ROLE_KEY=secretref:supabase-service-role-key \
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
- Submit a free-text brief with CRM and GA4 CSV uploads and receive a sourced media-plan document.
- Audit trace shows `brief`, `research`, `audience`, `performance`, and `strategy` in order.
- Markdown export downloads a non-empty media plan.
- Analyst approval is rejected or hidden.
- Admin can approve or reject the pending document approval.

The legacy Phase 2 `/api/analyze` route may remain available for baseline regression checks, but
Phase 3 smoke should focus on `POST /api/media-plan`.
