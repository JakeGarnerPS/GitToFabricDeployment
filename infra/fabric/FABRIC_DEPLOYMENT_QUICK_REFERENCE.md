# Fabric Deployment Pipeline - Quick Reference

## 📋 Deployment Files

| File | Purpose |
|------|---------|
| `infra/fabric-deployment-pipelines.json` | Pipeline definition with stages & policies |
| `infra/fabric-deployment-config.json` | Detailed deployment configuration |
| `scripts/deploy_fabric_pipeline.py` | Python CLI for managing pipelines |

## 🚀 Quick Commands

### 1. Authenticate
```bash
az login
az account show  # Verify you're logged in
```

### 2. Get Workspace IDs
```bash
jq -r '.Road4_Bronze_Dev' infra/workspace_ids.json
# Returns: workspace-id for Dev Bronze workspace
```

### 3. Create Deployment Pipeline
```bash
python scripts/deploy_fabric_pipeline.py \
  --action create \
  --config infra/fabric-deployment-pipelines.json
```

### 4. List Pipelines
```bash
python scripts/deploy_fabric_pipeline.py \
  --action list
```

### 5. Check Pipeline Status
```bash
python scripts/deploy_fabric_pipeline.py \
  --action status \
  --pipeline-id <pipeline-id>
```

### 6. Promote Dev → Staging
```bash
python scripts/deploy_fabric_pipeline.py \
  --action promote \
  --pipeline-id <pipeline-id> \
  --from-stage <dev-stage-id> \
  --to-stage <staging-stage-id>
```

### 7. Promote Staging → Prod
```bash
python scripts/deploy_fabric_pipeline.py \
  --action promote \
  --pipeline-id <pipeline-id> \
  --from-stage <staging-stage-id> \
  --to-stage <prod-stage-id>
```

## 🔄 Deployment Flow

```
┌─ Development
│  ├─ Make changes in Dev workspaces
│  ├─ Test in Notebooks/Pipelines
│  └─ Validate items
│
├─ Staging (Requires Approval)
│  ├─ Promote from Dev
│  ├─ Run acceptance tests
│  └─ Get stakeholder approval
│
└─ Production (Requires Approval)
   ├─ Promote from Staging
   ├─ Monitor deployment
   └─ Verify data/reports
```

## 📊 Workspace Mapping

### Dev Workspaces
- `Road4_Bronze_Dev` - Bronze layer development
- `Road4_Silver_Dev` - Silver layer development
- `Road4_Gold_Dev` - Gold layer development

### Staging Workspaces
- `Road4_Bronze_Staging` - Bronze layer staging
- `Road4_Silver_Staging` - Silver layer staging
- `Road4_Gold_Staging` - Gold layer staging

### Production Workspaces
- `Road4_Bronze` - Bronze layer production
- `Road4_Silver` - Silver layer production
- `Road4_Gold` - Gold layer production

## 🔑 Key Concepts

### Stages
- **Dev**: Development environment, quick iteration, no approval needed
- **Staging**: Pre-production, requires 1 approver, acceptance testing
- **Prod**: Production, requires 2+ approvers, minimal changes

### Items
- Notebooks
- Data Pipelines (formerly Notebooks with orchestration)
- Lakehouses (schemas only, not data)
- Reports (if applicable)

### Deployment Options
- **Replace**: Overwrite existing items in target
- **Validate**: Check syntax and references before deploy
- **Compare**: See differences between stages
- **Rollback**: Revert to previous deployment

## 📈 Typical Workflow

### Day 1: Development
```bash
# Work in Dev workspaces
# - Update notebooks
# - Modify pipelines
# - Test changes
# - Fix issues
```

### Day 2: Testing & Approval
```bash
# Promote to Staging
python scripts/deploy_fabric_pipeline.py --action promote \
  --pipeline-id <id> \
  --from-stage <dev-id> --to-stage <staging-id>

# Acceptance tests
# - Run E2E tests
# - Validate data
# - Performance checks
# - Get approval
```

### Day 3: Production
```bash
# Promote to Production
python scripts/deploy_fabric_pipeline.py --action promote \
  --pipeline-id <id> \
  --from-stage <staging-id> --to-stage <prod-id>

# Monitor
# - Check dashboard refreshes
# - Verify data completeness
# - Monitor performance
```

## 🛑 Approval Gates

| Stage | Approvers | Items Needed | Time |
|-------|-----------|-------------|------|
| Dev | - | None | - |
| Staging | 1 peer reviewer | Comment on change | <1 day |
| Prod | 2 leads (+ platform) | Formal approval | <2 hours |

## 🔐 Permission Levels

### Dev Stage
- Developers: Can edit items
- Testers: Can view/run items
- Power Users: Can modify configuration

### Staging Stage
- Team Leads: Can edit/promote
- Developers: View only
- QA: Can run tests

### Production Stage
- Platform Team: Admin only
- Data Leads: Can promote (with approval)
- Business: View/consume only

## ⚠️ Common Scenarios

### Scenario 1: Emergency Hotfix
```bash
# Quick fix needed in Prod
# 1. Fix in Dev
# 2. Test locally
# 3. Request emergency approval for Staging
# 4. Promote to Staging (fast-track)
# 5. Request emergency approval for Prod
# 6. Promote to Prod
# 7. Backfill same fix to next Dev release
```

### Scenario 2: Batch Release
```bash
# Multiple changes ready
# 1. Combine all changes in Dev
# 2. Run full test suite
# 3. Promote all items together to Staging
# 4. Acceptance testing
# 5. Promote all to Prod
# 6. Single deployment notification
```

### Scenario 3: Rollback
```bash
# Something wrong in Prod
# 1. Find last good deployment in history
# 2. Re-promote that version back to Prod
# 3. Investigate issue in Dev/Staging
# 4. Fix and redeploy when ready
```

## 📝 Configuration

### View Configuration
```bash
cat infra/fabric-deployment-pipelines.json | jq '.pipelines'
cat infra/fabric-deployment-config.json | jq '.deploymentOptions'
```

### Edit Configuration
1. Edit JSON files locally
2. Update pipeline settings in Fabric UI
3. Re-run deployment with new config

### Key Settings
```json
{
  "validation": true,
  "replaceItems": true,
  "updateConnectionStrings": false,
  "preserveConnectionStrings": true,
  "autoRollback": true
}
```

## 🆘 Troubleshooting

### "Cannot find workspace"
```bash
# Verify workspace ID
jq -r '.Road4_Bronze_Dev' infra/workspace_ids.json

# Check if ID is valid (not "null")
# If null, run deployment script first
```

### "Deployment validation failed"
```bash
# Check error in Fabric UI details
# Fix issue in source workspace
# Re-run promotion
```

### "Permission denied"
```bash
# Verify you have edit rights in source stage
# Check if deployment requires approval
# Request from approval queue in Fabric UI
```

### "Items not deploying"
```bash
# Ensure items exist in source stage
# Check if items have dependencies
# Verify connection strings are correct
```

## 📚 Related Documentation

- **Full Guide**: `infra/FABRIC_NATIVE_DEPLOYMENT.md`
- **Pipeline Config**: `infra/fabric-deployment-pipelines.json`
- **Deployment Config**: `infra/fabric-deployment-config.json`
- **Python Script**: `scripts/deploy_fabric_pipeline.py`
- **Microsoft Docs**: https://learn.microsoft.com/en-us/fabric/cicd/deployment-pipelines/

## 💡 Tips

1. **Test in Dev first** - Always test changes before promoting
2. **Use meaningful names** - Version numbers in notebook names help tracking
3. **Document approvals** - Add comments when promoting between stages
4. **Monitor deployments** - Check status after each promotion
5. **Keep backups** - Export important items before deployment
6. **Batch changes** - Group related items in single promotion
7. **Schedule deployments** - Promote during maintenance windows
8. **Train team** - Everyone should understand approval workflow

## ✅ Deployment Checklist

Before promoting to Prod:
- [ ] Changes tested in Dev
- [ ] All tests passing
- [ ] Code reviewed and approved
- [ ] Staged for acceptance testing
- [ ] Business approval obtained
- [ ] No breaking changes
- [ ] Rollback plan documented
- [ ] Stakeholders notified
- [ ] Maintenance window scheduled
- [ ] Monitoring configured

## 🎯 Best Practices

1. **One-way promotion**: Dev → Staging → Prod (no back-and-forth)
2. **Frequent small releases**: Better than big infrequent ones
3. **Automate testing**: Validate before manual approval
4. **Clear change tracking**: Use deployment comments
5. **Document decisions**: Keep approval notes
6. **Monitor post-deployment**: Check dashboards/queries work
7. **Regular backups**: Export before major deployments
8. **Team communication**: Notify users of deployments

---

**Quick Links**:
- [Full Documentation](./FABRIC_NATIVE_DEPLOYMENT.md)
- [Deployment Config](./fabric-deployment-pipelines.json)
- [Setup Guide](./DEPLOYMENT_SETUP_SUMMARY.md)
