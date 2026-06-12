#!/usr/bin/env python3
"""
Deploy Lakehouse and Sample Data to Microsoft Fabric
This script creates a lakehouse and uploads sample data files to Fabric.
"""

import os
import sys
import json
import argparse
from pathlib import Path
import requests
from typing import Optional

from medallion.lakehouse import LakehouseClient

# Configuration
FABRIC_API_BASE_URL = "https://api.fabric.microsoft.com/v1"
LAKEHOUSE_NAME = "medallion_lakehouse"
SAMPLE_DATA_FILE = "data/sample_raw_sales.csv"
SAMPLE_DATA_FOLDER = "raw"


def get_access_token_interactive() -> str:
    """
    Get access token interactively using Azure CLI
    
    Returns:
        Access token
    """
    print("Attempting to get access token via Azure CLI...")
    import subprocess
    
    try:
        result = subprocess.run(
            ["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com"],
            capture_output=True,
            text=True,
            check=True
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
        print("\n💡 Alternative: Run with explicit token:")
        print("   python scripts/deploy_lakehouse.py --workspace-id <ID> --token <TOKEN>")
        sys.exit(1)
    except subprocess.CalledProcessError:
        print("❌ Failed to get access token. Make sure you're logged in with: az login")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Deploy lakehouse and sample data to Microsoft Fabric",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/deploy_lakehouse.py --workspace-id <id> --token <token>
  python scripts/deploy_lakehouse.py --workspace-id <id> --interactive
        """
    )
    
    parser.add_argument(
        "--workspace-id",
        required=True,
        help="Fabric workspace ID"
    )
    
    parser.add_argument(
        "--token",
        help="Azure access token (if not provided, will use interactive login)"
    )
    
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Get token interactively via Azure CLI"
    )
    
    parser.add_argument(
        "--lakehouse-name",
        default=LAKEHOUSE_NAME,
        help=f"Name of the lakehouse (default: {LAKEHOUSE_NAME})"
    )
    
    parser.add_argument(
        "--sample-data-file",
        default=SAMPLE_DATA_FILE,
        help=f"Path to sample data file (default: {SAMPLE_DATA_FILE})"
    )
    
    args = parser.parse_args()
    
    # Get access token
    if args.interactive:
        access_token = get_access_token_interactive()
    elif args.token:
        access_token = args.token
    else:
        print("❌ Please provide --token or use --interactive")
        sys.exit(1)
    
    print("🚀 Starting Fabric deployment...")
    
    # Initialize client
    client = LakehouseClient(args.workspace_id, access_token)
    
    # Check if lakehouse exists
    print(f"\n📋 Checking for existing lakehouse '{args.lakehouse_name}'...")
    existing_lakehouse = client.get_lakehouse(args.lakehouse_name)
    
    if existing_lakehouse:
        print(f"✅ Lakehouse '{args.lakehouse_name}' already exists")
        lakehouse_id = existing_lakehouse["id"]
    else:
        print(f"📝 Creating lakehouse '{args.lakehouse_name}'...")
        response = client.create_lakehouse(args.lakehouse_name)
        lakehouse_id = response["id"]
        print(f"✅ Lakehouse created with ID: {lakehouse_id}")
    
    # Upload sample data
    if os.path.exists(args.sample_data_file):
        print(f"\n📤 Uploading sample data from '{args.sample_data_file}'...")
        target_folder = f"Files/{SAMPLE_DATA_FOLDER}"
        
        try:
            client.upload_file_to_lakehouse(
                lakehouse_id,
                args.sample_data_file,
                target_folder
            )
            print(f"✅ Sample data uploaded to '{target_folder}' folder")
        except Exception as e:
            print(f"⚠️  Warning: Could not upload file: {e}")
            print("   You can manually upload the sample data later")
    else:
        print(f"⚠️  Sample data file not found: {args.sample_data_file}")
    
    print("\n✨ Deployment complete!")
    print(f"   Workspace ID: {args.workspace_id}")
    print(f"   Lakehouse ID: {lakehouse_id}")
    print(f"   Lakehouse Name: {args.lakehouse_name}")


if __name__ == "__main__":
    main()
