#!/usr/bin/env python3
"""Deploy the full medallion stack from the shared params file."""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from deploy_lakehouse import deploy_lakehouse, get_access_token_interactive
from deploy_medallion_workspaces import main as deploy_medallion_workspaces_main
from deploy_notebooks import main as deploy_notebooks_main
from assign_workspaces_to_capacity import main as assign_workspaces_to_capacity_main
from medallion.utils import load_params_file, resolve_tier_workspace_name

REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_PARAMS_FILE = REPO_ROOT / "infra" / "medallion" / "medallion_workspace_params.json"


def collect_deployment_targets(params: Dict[str, Any], tiers: List[str], environments: List[str]) -> List[Dict[str, Any]]:
    prefix = params.get("prefix", "Road4")
    prod_environment = params.get("prod_environment", "Prod")
    workspace_names = params.get("workspace_names", {})
    tier_lakehouses = params.get("tier_lakehouses", {})

    targets: List[Dict[str, Any]] = []
    for tier in tiers:
        for environment in environments:
            workspace_name = resolve_tier_workspace_name(
                tier,
                environment,
                prefix,
                prod_environment,
                workspace_names,
            )
            lakehouse_name = tier_lakehouses.get(tier.lower()) or f"{tier.lower()}_lakehouse"
            targets.append(
                {
                    "tier": tier,
                    "environment": environment,
                    "workspace_name": workspace_name,
                    "lakehouse_name": lakehouse_name,
                }
            )
    return targets


def main() -> None:
    if len(sys.argv) > 1:
        print("This script uses the params file and does not accept command line arguments.")
        sys.exit(1)

    access_token = os.environ.get("FABRIC_ACCESS_TOKEN") or os.environ.get("AZURE_ACCESS_TOKEN")
    if not access_token:
        access_token = get_access_token_interactive()

    params_path = DEFAULT_PARAMS_FILE
    params = load_params_file(str(params_path))
    tiers = [tier.strip() for tier in params.get("tiers", "Bronze,Silver,Gold").split(",") if tier.strip()]
    environments = [environment.strip() for environment in params.get("environments", "Dev,Prod,Staging,Feature").split(",") if environment.strip()]

    targets = collect_deployment_targets(params, tiers, environments)
    print(f"🚀 Deploying {len(targets)} medallion targets from {params_path}")

    print("\n🧱 Deploying medallion workspaces...")
    deploy_medallion_workspaces_main()

    for target in targets:
        print(f"\n📦 {target['tier']} / {target['environment']} → {target['workspace_name']}")
        deploy_lakehouse(
            access_token,
            params_path=params_path,
            tier=target["tier"],
            environment=target["environment"],
            workspace_name=target["workspace_name"],
            lakehouse_name=target["lakehouse_name"],
        )

    print("\n📓 Deploying notebooks...")
    deploy_notebooks_main()

    print("\n⚙️ Assigning workspaces to capacity...")
    assign_workspaces_to_capacity_main()

    print("\n✨ Full deployment run complete")


if __name__ == "__main__":
    main()
