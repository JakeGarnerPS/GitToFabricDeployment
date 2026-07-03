#!/usr/bin/env python3

import os
from pathlib import Path
from typing import List

from medallion.client import FabricClient
from medallion.lakehouse import LakehouseClient
from medallion.utils import (
    get_access_token_interactive,
    load_params_file,
    resolve_tier_workspace_name,
)


DEFAULT_PARAMS_FILE = Path(__file__).resolve().parents[2] / "infra" / "medallion" / "medallion_workspace_params.json"


def _split_csv(raw: str, default: str) -> List[str]:
    return [v.strip() for v in (raw or default).split(",") if v.strip()]


def main() -> None:
    token = os.environ.get("FABRIC_ACCESS_TOKEN") or os.environ.get("AZURE_ACCESS_TOKEN")
    if not token:
        token = get_access_token_interactive()

    client = FabricClient(token)

    params = load_params_file(str(DEFAULT_PARAMS_FILE)) or {}

    prefix = params.get("prefix", "Road4")
    prod_environment = params.get("prod_environment", "Prod")
    workspace_names = params.get("workspace_names", {})
    tiers = _split_csv(params.get("tiers"), "Bronze,Silver,Gold")
    environments = _split_csv(params.get("environments"), "Dev,Prod,Staging,Feature")
    description = params.get("workspace_description", "Managed by new_deployer.py")
    capacity_id = params.get("capacity_id")

    print(f"Using params: {DEFAULT_PARAMS_FILE}")
    print(f"Will ensure {len(tiers) * len(environments)} workspaces")

    for tier in tiers:
        for environment in environments:
            workspace_name = resolve_tier_workspace_name(
                tier, environment, prefix, prod_environment, workspace_names
            )
            print(f"⏳ Ensuring workspace: {workspace_name}")
            try:
                # Deploy workspace
                ws = client.get_or_create_workspace(workspace_name, description=description, capacity_id=capacity_id)
                print(f"   ✅ Ready: {ws.get('displayName')} ({ws.get('id')})")

                # Get Created workspace ID                
                workspace_id = ws.get('id')

                # Deploy lakehouse
                workspace_client = LakehouseClient(workspace_id, token)   
                resolved_lakehouse_name = params.get("tier_lakehouses", {}).get(tier.lower()) or f"{tier.lower()}_lakehouse"
                response = workspace_client.get_or_create_lakehouse(workspace_id, resolved_lakehouse_name)                
                lakehouse_id = response.get("id")

                print(f"   ✅ Lakehouse deployed in workspace: {workspace_name}")


            except Exception as err:
                print(err)


if __name__ == "__main__":
    main()
