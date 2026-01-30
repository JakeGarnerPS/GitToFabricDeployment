# Deployment Guide ✅

This guide shows how to configure GitHub Actions to deploy the Node app to Azure Web App.

## Prerequisites

- Azure subscription and appropriate permissions
- Azure CLI installed and logged in (`az login`)
- GitHub repository admin access to add secrets
- Ensure `server.js` listens on `process.env.PORT || 8080`

## 1) Provision resources (example)

```bash
az group create -n my-app-rg -l westeurope
az appservice plan create -g my-app-rg -n my-app-plan --sku B1 --is-linux
az webapp create -g my-app-rg -p my-app-plan -n my-app --runtime "NODE|18-lts"
```

## 2) Create an Azure service principal (for GitHub Actions)

Replace placeholders with your subscription ID and resource group.

```bash
az ad sp create-for-rbac --name "github-action-deployer-$(date +%s)" \
  --role contributor \
  --scopes /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/my-app-rg \
  --sdk-auth
```

Copy the JSON output and add it to your repository's GitHub Secrets as `AZURE_CREDENTIALS`.

## 3) Add repository secrets

- `AZURE_CREDENTIALS` — JSON output from `az ad sp create-for-rbac --sdk-auth`
- `AZURE_WEBAPP_NAME` — name of the Web App created (e.g., `my-app`)

Optional alternative: use `AZURE_PUBLISH_PROFILE` (the publish profile XML content) and `azure/webapps-deploy` `publish-profile` input.

## 4) Automatic provisioning via GitHub Actions 🔁

A `provision-infra` job runs automatically on pushes to `main` and will create the following resources (idempotently) using the Bicep template `infra/main.bicep`:

- Resource group: `my-app-rg`
- App Service plan: `my-app-plan` (sku: `B1`, Linux)
- Web App: `my-app` (Node 18 runtime)
- App settings: `APP_ENV`, `LOG_LEVEL`, `PORT`

This job uses the same `AZURE_CREDENTIALS` secret and requires the service principal to have sufficient permissions to create resources in the subscription. The job runs `az deployment group create --resource-group <rg> --template-file infra/main.bicep` and passes parameters such as `webAppName` (set from the `AZURE_WEBAPP_NAME` secret or defaulted in the workflow).

To deploy locally with the Bicep template:

```bash
az group create -n my-app-rg -l westeurope
az deployment group create -g my-app-rg -f infra/main.bicep --parameters webAppName=my-app
```

---

If you'd like, I can also add a parameter file (`infra/parameters.json`) so you can keep environment-specific values in source control. Would you like that? (yes/no)
## 4) Push to `main`

The workflow `.github/workflows/deploy.yml` triggers on pushes to `main` and will:
- Install dependencies in `src/app`
- Zip the app and deploy to the configured Azure Web App

---

If you'd like, I can also:
- Add automatic resource creation via an ARM/Bicep template
- Add a `build` script and test step to the workflow

Tell me which of those you'd like to add next. 🎯