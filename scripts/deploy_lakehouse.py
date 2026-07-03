#!/usr/bin/env python3
"""
Deploy a medallion lakehouse and sample data to Microsoft Fabric.

The target workspace and lakehouse are resolved from
infra/medallion/medallion_workspace_params.json unless the caller provides
explicit CLI overrides.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from medallion.lakehouse import LakehouseClient
from medallion.utils import load_params_file, resolve_tier_workspace_name

REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_PARAMS_FILE = REPO_ROOT / "infra" / "medallion" / "medallion_workspace_params.json"
DEFAULT_SAMPLE_DATA_FILE = REPO_ROOT / "data" / "sample_raw_sales.csv"
DEFAULT_SAMPLE_DATA_FOLDER = "raw"


def deploy_lakehouse(
    access_token: str,
    params_path: Path = DEFAULT_PARAMS_FILE,
    tier: str = "Bronze",
    environment: str | None = None,
    workspace_name: str | None = None,
    lakehouse_name: str | None = None,
    sample_data_path: Path | None = None,
) -> None:
    params = load_params_file(str(params_path))

    prefix = params.get("prefix", "Road4")
    prod_environment = params.get("prod_environment", "Prod")
    workspace_names = params.get("workspace_names", {})
    tier_lakehouses = params.get("tier_lakehouses", {})

    resolved_environment = environment or prod_environment
    resolved_workspace_name = workspace_name or resolve_tier_workspace_name(
        tier,
        resolved_environment,
        prefix,
        prod_environment,
        workspace_names,
    )
    resolved_lakehouse_name = lakehouse_name or tier_lakehouses.get(tier.lower()) or f"{tier.lower()}_lakehouse"

    print("🚀 Starting Fabric lakehouse deployment...")
    print(f"   Params file: {params_path}")
    print(f"   Tier: {tier}")
    print(f"   Environment: {resolved_environment}")
    print(f"   Workspace: {resolved_workspace_name}")
    print(f"   Lakehouse: {resolved_lakehouse_name}")

    client = LakehouseClient("", access_token)
    workspace = client.get_workspace_by_name(resolved_workspace_name)
    if not workspace:
        print(f"❌ Workspace '{resolved_workspace_name}' was not found.")
        sys.exit(1)

    workspace_id = workspace["id"]
    print(f"✅ Resolved workspace '{resolved_workspace_name}' to ID {workspace_id}")

    workspace_client = LakehouseClient(workspace_id, access_token)

    print(f"\n📋 Checking for existing lakehouse '{resolved_lakehouse_name}'...")
    try:
        existing_lakehouse = workspace_client.get_lakehouse(resolved_lakehouse_name)
    except Exception as error:
        print(f"⚠️  Could not inspect lakehouses in workspace: {error}")
        existing_lakehouse = None

    if existing_lakehouse:
        print(f"✅ Lakehouse '{resolved_lakehouse_name}' already exists")
        lakehouse_id = existing_lakehouse["id"]
    else:
        print(f"📝 Creating lakehouse '{resolved_lakehouse_name}'...")
        try:
            response = workspace_client.create_lakehouse(resolved_lakehouse_name)
            lakehouse_id = response.get("id")
            print(f"✅ Lakehouse created with ID: {lakehouse_id}")
        except Exception as error:
            print(f"⚠️  Could not create lakehouse: {error}")
            lakehouse_id = None

    deployment_data_path = sample_data_path or DEFAULT_SAMPLE_DATA_FILE
    if deployment_data_path.exists():
        print(f"\n📤 Uploading sample data from '{deployment_data_path}'...")
        target_folder = f"Files/{DEFAULT_SAMPLE_DATA_FOLDER}"
        try:
            workspace_client.upload_file_to_lakehouse(lakehouse_id, str(deployment_data_path), target_folder)
            print(f"✅ Sample data uploaded to '{target_folder}' folder")
        except Exception as error:
            print(f"⚠️  Warning: Could not upload file: {error}")
            print("   You can manually upload the sample data later")
    else:
        print(f"⚠️  Sample data file not found: {deployment_data_path}")

    print("\n✨ Deployment complete!")
    print(f"   Workspace ID: {workspace_id}")
    print(f"   Lakehouse ID: {lakehouse_id}")
    print(f"   Lakehouse Name: {resolved_lakehouse_name}")


def get_access_token_interactive() -> str:
    """Get an access token interactively using Azure CLI."""
    print("Attempting to get access token via Azure CLI...")

    try:
        result = subprocess.run(
            ["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com"],
            capture_output=True,
            text=True,
            check=True,
        )
        token_data = json.loads(result.stdout)
        return token_data["accessToken"]
    except FileNotFoundError:
        print("\n❌ Azure CLI not found in this environment.")
        print("\n📋 To get your access token manually:")
        print("   1. Go to: https://microsoft.com/devicelogin")
        print("   2. Enter the code shown when you run this script")
        print("   3. Or get a token from Azure Portal:")
        print("      - Go to: https://portal.azure.com")
        print("      - Azure Active Directory → App registrations")
        print("      - Get a token for resource: https://api.fabric.microsoft.com")
        print("\n💡 Alternative: Run with an explicit token:")
        print("   python scripts/deploy_lakehouse.py --token <TOKEN> --tier Bronze --environment Prod")
        sys.exit(1)
    except subprocess.CalledProcessError:
        print("❌ Failed to get access token. Make sure you're logged in with: az login")
        sys.exit(1)


def main() -> None:
    if len(sys.argv) > 1:
        print("This script uses the params file and does not accept command line arguments.")
        sys.exit(1)

    access_token = os.environ.get("FABRIC_ACCESS_TOKEN") or os.environ.get("AZURE_ACCESS_TOKEN")
    if not access_token:
        access_token = get_access_token_interactive()

    params_path = DEFAULT_PARAMS_FILE
    deploy_lakehouse(access_token, params_path=params_path)


if __name__ == "__main__":
    main()
