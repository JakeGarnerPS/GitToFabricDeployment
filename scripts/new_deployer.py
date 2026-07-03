#!/usr/bin/env python3

import os
from pathlib import Path
from typing import List

from medallion.notebooks import NotebooksClient, load_notebook_content
from medallion.client import FabricClient
from medallion.lakehouse import LakehouseClient
from medallion.fabric_pipeline import FabricDeploymentClient
from medallion.utils import (
    get_access_token_interactive,
    load_params_file,
    resolve_tier_workspace_name,
)
from deploy_lakehouse import deploy_lakehouse


DEFAULT_PARAMS_FILE = Path(__file__).resolve().parents[1] / "infra" / "medallion" / "medallion_workspace_params.json"
DEFAULT_DEPLPYMENT_PIPELINE_CONFIG = Path(__file__).resolve().parents[1] / "infra" / "fabric" / "fabric-deployment-pipelines.json"


def _split_csv(raw: str, default: str) -> List[str]:
    return [v.strip() for v in (raw or default).split(",") if v.strip()]


def main() -> None:
    token = os.environ.get("FABRIC_ACCESS_TOKEN") or os.environ.get("AZURE_ACCESS_TOKEN")
    if not token:
        token = get_access_token_interactive()

    client = FabricClient(token)

    params = load_params_file(str(DEFAULT_PARAMS_FILE)) or {}
    deployment_pipeline_config = load_params_file(str(DEFAULT_DEPLPYMENT_PIPELINE_CONFIG)) or {}


    prefix = params.get("prefix", "Road4")
    prod_environment = params.get("prod_environment", "Prod")
    workspace_names = params.get("workspace_names", {})
    tiers = _split_csv(params.get("tiers"), "Bronze,Silver,Gold")
    environments = _split_csv(params.get("environments"), "Dev,Prod,Staging,Feature")
    capacity_id = params.get("capacity_id")
    description = params.get("workspace_description", "Managed by new_deployer.py")
    notebooks = params.get("tier_notebooks", {})
    pipelines = params.get("tier_pipelines", {})

    print(f"Using params: {DEFAULT_PARAMS_FILE}")
    print(f"Will ensure {len(tiers) * len(environments)} workspaces and lakehouses")

    #Testing 
    tiers =["Bronze"]
    environments = ["Dev"]
    print(capacity_id)
    
        
    for tier in tiers:
        
        for environment in environments:
            workspace_name = resolve_tier_workspace_name(
                tier, environment, prefix, prod_environment, workspace_names
            )
            print(f"\n⏳ Ensuring workspace: {workspace_name}")
            try:
                # Deploy workspace and assign capacity if configured
                ws = client.get_or_create_workspace(workspace_name, description=description, capacity_id=capacity_id)
                workspace_id = ws.get("id")
              
                # Deploy lakhouse
                print(f"⏳ Ensuring lakehouse for workspace: {workspace_name}")
                workspace_client = LakehouseClient(workspace_id, token)
                resolved_lakehouse_name = f"{tier.lower()}_lakehouse"
                response = workspace_client.create_lakehouse(resolved_lakehouse_name)
                lakehouse_id = response.get("id")

                # Deploy notebooks for the tier
                nb_client = NotebooksClient(workspace_id, token)
                existing_list = nb_client.get_notebooks()
                existing_names = {nb.get('displayName', '').lower() for nb in existing_list}

                for notebook in notebooks.get(tier, []):
                    notebook_name = notebook.lower()
                    if notebook_name in existing_names:
                        print(f"⚠️  Notebook {notebook} already exists in workspace. Skipping deployment.")
                        continue

                    print(f"⏳ Deploying notebook: {notebook} to {tier} tier")
                    nb_path = os.path.join(f"{tier}/Notebooks", notebook)

                    try:
                        content = load_notebook_content(nb_path)
                        nb_client.create_notebook(notebook, content)
                        print(f"✅ Successfully deployed notebook: {notebook}")
                    except Exception as err:
                        print(f"❌ Error deploying notebook {notebook}: {err}")

                # Deploy pipelines for the tier
                pl_client = FabricDeploymentClient(token)

                for pipeline in pipelines.get(tier, []):
                    print(f"⏳ Deploying pipeline: {pipeline} to {tier} tier")
                    try:                       
                        pipeline = pl_client.create_deployment_pipeline(deployment_pipeline_config)
                        print(f"✅ Successfully deployed pipeline: {pipeline}")

                    except Exception as err:
                        print(f"❌ Error deploying pipeline {pipeline}: {err}")
               

            except Exception as err:
                print(f"❌ Error ensuring workspace or lakehouse: {err}")
                continue

if __name__ == "__main__":
    main()
