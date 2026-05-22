# Fabric Deployment Pipeline Guide

## Overview

This guide explains how to use the native Fabric Deployment Pipeline feature to promote your medallion architecture workspaces across environments (Dev → Staging → Prod).

## What is a Fabric Deployment Pipeline?

A **Deployment Pipeline** in Microsoft Fabric is a native feature that allows you to:

- 🔄 **Promote content** across multiple stages (Dev, Staging, Prod)
- ✅ **Validate items** before deployment
- 🔐 **Control permissions** per stage
- 👥 **Require approvals** for production deployments
- 📊 **Compare content** between stages
- 🔙 **Rollback deployments** if needed

## Architecture

```
Development Workspace    Staging Workspace      Production Workspace
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ Bronze_Dev       │    │ Bronze_Staging   │    │ Bronze           │
│ Silver_Dev       │───▶│ Silver_Staging   │───▶│ Silver           │
│ Gold_Dev         │    │ Gold_Staging     │    │ Gold             │
└──────────────────┘    └──────────────────┘    └──────────────────┘
       ▲                      ▲                       ▲
       │                      │                       │
   Notebooks              Notebooks               Notebooks
   Pipelines              Pipelines               Pipelines
   Lakehouses             Lakehouses             Lakehouses
```

## Files Created

### 1. `infra/fabric-deployment-pipelines.json`

Main deployment pipeline definition with:
- **Stages**: Dev, Staging, Prod
- **Policies**: Validation, promotion, approvals, notifications
- **Workspace mappings**: All 12 workspaces (4 tiers × 3 environments)
- **Deployment rules**: Dev→Staging and Staging→Prod promotion rules
- **Approval gates**: Require approvers for Staging and Prod

### 2. `infra/fabric-deployment-config.json`

Detailed deployment configuration for Fabric REST API with:
- **Stage-by-stage** item definitions
- **Deployment options**: Validation, backup, rollback settings
- **Notifications**: Email and Teams integration
- **Schedule**: Deployment windows and maintenance times
- **Rollback policy**: Automatic failure recovery

### 3. `scripts/deploy_fabric_pipeline.py`

Python script to manage deployment pipelines programmatically:
- Create deployment pipelines
- Promote items between stages
- Monitor deployment status
- List and manage pipelines

## Getting Started

### Step 1: Set Up Fabric Access

```bash
# Authenticate with Azure
az login

# Verify Fabric access
az account show
```

### Step 2: Create a Deployment Pipeline

You can create a deployment pipeline through:

#### Option A: Fabric UI (Manual)

1. Go to **Fabric Home** → **Create** → **Deployment Pipeline**
2. Name it "Medallion_Deployment_Pipeline"
3. Add three stages: Dev, Staging, Prod
4. Connect each stage to the corresponding workspace:
   - Dev Stage → Road4_Bronze_Dev, Road4_Silver_Dev, Road4_Gold_Dev
   - Staging Stage → Road4_Bronze_Staging, Road4_Silver_Staging, Road4_Gold_Staging
   - Prod Stage → Road4_Bronze, Road4_Silver, Road4_Gold

#### Option B: REST API (Automated)

Get your workspace ID:
```bash
jq -r '.Road4_Bronze_Dev' infra/workspace_ids.json
```

Create the pipeline:
```bash
python scripts/deploy_fabric_pipeline.py \
  --action create \
  --config infra/fabric-deployment-pipelines.json
```

### Step 3: Configure Stages

For each stage, you can configure:

1. **Who can edit**: Set users who can modify items
2. **Approval requirements**: Enable/disable approvals
3. **Deployment rules**: What happens when promoting to next stage

## Deployment Workflow

### Promoting from Dev to Staging

```bash
python scripts/deploy_fabric_pipeline.py \
  --action promote \
  --pipeline-id <pipeline-id> \
  --from-stage <dev-stage-id> \
  --to-stage <staging-stage-id>
```

This will:
1. ✅ Validate all items in Dev stage
2. 📋 Compare items with Staging
3. 🔄 Deploy items to Staging workspace
4. 📊 Generate comparison report

### Promoting from Staging to Prod

```bash
python scripts/deploy_fabric_pipeline.py \
  --action promote \
  --pipeline-id <pipeline-id> \
  --from-stage <staging-stage-id> \
  --to-stage <prod-stage-id>
```

**Requirements:**
- Approvals from designated reviewers (in Fabric UI)
- Validation passes with no errors
- No breaking changes to data models

## Monitoring Deployments

### Check Pipeline Status

```bash
python scripts/deploy_fabric_pipeline.py \
  --action status \
  --pipeline-id <pipeline-id>
```

### View Deployment History

In Fabric UI:
1. Open your Deployment Pipeline
2. Click **Deployment History**
3. See all promotions with timestamps and status

### Handle Deployment Failures

If a deployment fails:

1. **Check the error** in deployment details
2. **Fix the issue** (e.g., in Dev workspace)
3. **Retest** in Dev stage
4. **Promote again** when ready

The deployment pipeline logs:
- What items were deployed
- Any validation errors
- Conflicts with existing items
- Connection string updates

## Configuration Reference

### fabric-deployment-pipelines.json Structure

```json
{
  "stages": [
    {
      "name": "Development",
      "order": 1
    }
  ],
  "policies": {
    "itemValidation": {
      "enabled": true,
      "rules": [...]
    },
    "promotion": {
      "requiresApproval": true,
      "stageApprovals": {
        "Dev": { "required": false },
        "Staging": { "required": true },
        "Prod": { "required": true }
      }
    }
  },
  "workspaces": {
    "Bronze": { "Dev": {...}, "Staging": {...}, "Prod": {...} }
  }
}
```

### Key Settings

| Setting | Purpose | Dev | Staging | Prod |
|---------|---------|-----|---------|------|
| `requiresApproval` | Require approval to deploy | false | true | true |
| `validateBeforeDeploy` | Check items before promotion | true | true | true |
| `replaceItems` | Overwrite existing items | true | true | true |
| `preserveConnectionStrings` | Keep prod connections | false | false | true |

## Best Practices

### 1. Develop in Dev Stage
- Make all changes in Dev workspace
- Test thoroughly
- Fix issues before promoting

### 2. Test in Staging
- Run realistic tests
- Validate with production data (anonymized)
- Get stakeholder approval
- Performance testing

### 3. Deploy to Production
- Schedule during maintenance window
- Have rollback plan ready
- Monitor closely after deployment
- Document all changes

### 4. Stage Permissions
- **Dev**: All developers can edit
- **Staging**: Limited to team leads
- **Prod**: Only designated users can edit (mostly read-only)

### 5. Approval Process
- **Dev→Staging**: Peer review (1 approver)
- **Staging→Prod**: Leadership review (2+ approvers)
- Always include change notes
- Document approval decision

## Comparing Stages

In Fabric UI:
1. Open Deployment Pipeline
2. Select two stages to compare
3. View differences:
   - Items only in source stage
   - Items only in target stage
   - Items with different properties
   - Potential conflicts

## Rollback Strategy

If a production deployment goes wrong:

### Option 1: Redeploy Previous Version
```bash
# Check deployment history
python scripts/deploy_fabric_pipeline.py --action status ...

# Promote previous stable version from Staging back to Prod
```

### Option 2: Manual Fixes
1. Fix issues in Prod workspace directly
2. Backfill changes to Dev/Staging
3. Redeploy when stable

### Option 3: Full Restore
1. Restore from backup (if enabled)
2. Re-promote correct version
3. Verify all connections

## Advanced Scenarios

### Selective Item Promotion

Promote only specific items:
```bash
python scripts/deploy_fabric_pipeline.py \
  --action promote \
  --pipeline-id <id> \
  --from-stage <id> \
  --to-stage <id> \
  --items "notebook-1" "pipeline-1"
```

### Scheduled Deployments

Set up automated promotions:
```bash
# Add to cron job or Azure Function
# Deploy to Prod every Sunday 2 AM
0 2 * * 0 python scripts/deploy_fabric_pipeline.py --action promote ...
```

### Integration with CI/CD

After automated tests pass in GitHub Actions:
```bash
# Promote Dev→Staging automatically
# Then require manual approval for Prod
```

## Troubleshooting

### Issue: "Cannot promote - validation failed"
**Solution:**
1. Check error details in Fabric UI
2. Fix items in source stage
3. Re-test
4. Retry promotion

### Issue: "Deployment timed out"
**Solution:**
- Large deployments may take 10+ minutes
- Check Fabric capacity resources
- Try promoting fewer items at once

### Issue: "Permission denied"
**Solution:**
- Verify user has edit permissions in source stage
- Check if deployment requires approval
- Request approval from assigned reviewer

### Issue: "Connection string not updated"
**Solution:**
- Enable "updateConnectionStrings" in deployment options
- Verify target workspace has correct data source access
- Update connection string mapping in config

## Integration with Your Pipeline

### With GitHub Actions

```yaml
- name: Promote to Staging
  if: success()
  run: |
    python scripts/deploy_fabric_pipeline.py \
      --action promote \
      --pipeline-id $(jq -r '.pipeline_id' infra/workspace_ids.json) \
      --from-stage $(jq -r '.dev_stage_id' infra/workspace_ids.json) \
      --to-stage $(jq -r '.staging_stage_id' infra/workspace_ids.json)
```

### With Fabric Admin Monitoring

The deployment pipeline integrates with Fabric Admin Portal:
- View all deployments across workspaces
- Monitor deployment history
- Track user activities
- Audit all changes

## Next Steps

1. ✅ Create workspaces if not yet created
2. ✅ Create Deployment Pipeline in Fabric UI or via API
3. ✅ Configure stage permissions and approvals
4. ✅ Test promotion with a small item
5. ✅ Set up approval process
6. ✅ Document deployment procedures
7. ✅ Train team on promotion workflow

## Additional Resources

- [Microsoft Fabric Deployment Pipelines](https://learn.microsoft.com/en-us/fabric/cicd/deployment-pipelines/intro-to-deployment-pipelines)
- [Fabric REST API Reference](https://learn.microsoft.com/en-us/rest/api/fabric/)
- [Deployment Best Practices](https://learn.microsoft.com/en-us/fabric/cicd/deployment-pipelines/best-practices)
- [Troubleshooting Guide](https://learn.microsoft.com/en-us/fabric/cicd/deployment-pipelines/troubleshooting)

---

For more information, see the related files:
- Deployment config: `infra/fabric-deployment-config.json`
- Pipeline definition: `infra/fabric-deployment-pipelines.json`
- Deployment script: `scripts/deploy_fabric_pipeline.py`
