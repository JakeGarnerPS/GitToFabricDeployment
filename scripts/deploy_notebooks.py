#!/usr/bin/env python3
"""
Deploy Notebooks to Microsoft Fabric
This script uploads notebook files directly to a Fabric workspace.
"""

import os
import sys
import json
import argparse
import base64
from pathlib import Path
import requests
from typing import Optional

# Configuration
FABRIC_API_BASE_URL = "https://api.fabric.microsoft.com/v1"
NOTEBOOKS = [
    "Bronze/Notebooks/01_ingest_raw_sales.Notebook",
    "Bronze/Notebooks/01_ingest_raw_sales_python.Notebook",
    "Silver/Notebooks/02_clean_sales_data.Notebook",
    "Gold/Notebooks/03_curate_sales_mart.Notebook"
]


class FabricClient:
    """Client for interacting with Microsoft Fabric API"""
    
    def __init__(self, workspace_id: str, access_token: str):
        """
        Initialize Fabric client
        
        Args:
            workspace_id: Fabric workspace ID
            access_token: Azure access token for Fabric API
        """
        self.workspace_id = workspace_id
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    
    def create_notebook(self, name: str, content: str) -> dict:
        """
        Create a notebook in the workspace
        
        Args:
            name: Name of the notebook
            content: Notebook content as a string
            
        Returns:
            Response JSON with notebook details
        """
        url = f"{FABRIC_API_BASE_URL}/workspaces/{self.workspace_id}/notebooks"
        
        # Convert notebook to base64
        notebook_b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        payload = {
            "displayName": name,
            "definition": {
                "parts": [
                    {
                        "path": "notebook-content.py",
                        "payloadType": "InlineBase64",
                        "payload": notebook_b64
                    }
                ]
            }
        }
        
        response = requests.post(url, json=payload, headers=self.headers)
        
        if response.status_code != 202 and response.status_code != 201:
            print(f"   API Response: {response.status_code}")
            print(f"   Error: {response.text}")
        
        response.raise_for_status()
        
        # 202 Accepted responses may have empty body
        if response.status_code == 202:
            return {"id": name, "displayName": name, "status": "pending"}
        
        return response.json()

    def update_notebook(self, notebook_id: str, content: str) -> dict:
        """Update an existing notebook definition in-place."""
        notebook_b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')

        payload = {
            "definition": {
                "parts": [
                    {
                        "path": "notebook-content.py",
                        "payloadType": "InlineBase64",
                        "payload": notebook_b64
                    }
                ]
            }
        }

        endpoints = [
            f"{FABRIC_API_BASE_URL}/workspaces/{self.workspace_id}/notebooks/{notebook_id}/updateDefinition",
            f"{FABRIC_API_BASE_URL}/workspaces/{self.workspace_id}/items/{notebook_id}/updateDefinition",
        ]

        last_status = None
        last_error = ""

        for url in endpoints:
            response = requests.post(url, json=payload, headers=self.headers)
            if response.status_code in (404, 405):
                last_status = response.status_code
                last_error = response.text
                continue

            if response.status_code not in (200, 201, 202):
                print(f"   API Response: {response.status_code}")
                print(f"   Error: {response.text}")

            response.raise_for_status()

            if response.status_code == 202:
                return {"id": notebook_id, "status": "pending"}

            return response.json() if response.text else {"id": notebook_id, "status": "updated"}

        raise RuntimeError(
            "Unable to update notebook definition with available Fabric endpoints. "
            f"Last status: {last_status}, response: {last_error}"
        )
    
    def get_notebooks(self) -> list:
        """
        Get all notebooks in the workspace
        
        Returns:
            List of notebook details
        """
        url = f"{FABRIC_API_BASE_URL}/workspaces/{self.workspace_id}/notebooks"
        
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        
        return response.json().get("value", [])
    
    def get_notebook_by_name(self, name: str) -> Optional[dict]:
        """
        Get a notebook by display name
        
        Args:
            name: Display name of the notebook
            
        Returns:
            Notebook details or None if not found
        """
        notebooks = self.get_notebooks()
        
        for notebook in notebooks:
            if notebook.get("displayName") == name:
                return notebook
        
        return None


def load_notebook_content(file_path: str) -> str:
    """
    Load notebook content from a .Notebook folder or plain file
    
    Args:
        file_path: Path to a .Notebook folder or notebook file
        
    Returns:
        Notebook content as a string
    """
    if os.path.isdir(file_path):
        py_path = os.path.join(file_path, "notebook-content.py")
        if not os.path.exists(py_path):
            raise FileNotFoundError(f"notebook-content.py not found in: {file_path}")
        with open(py_path, 'r') as f:
            return f.read()

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Notebook file not found: {file_path}")
    
    with open(file_path, 'r') as f:
        return f.read()


def get_notebook_display_name(file_path: str) -> str:
    """
    Get display name from notebook file path
    
    Args:
        file_path: Path to .Notebook folder or notebook file
        
    Returns:
        Display name (folder name without .Notebook, or filename without extension)
    """
    name = Path(file_path).stem  # Removes .Notebook or .ipynb
    return name


def main():
    parser = argparse.ArgumentParser(
        description="Deploy notebooks to Microsoft Fabric",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/deploy_notebooks.py --workspace-id <id> --token <token>
  python scripts/deploy_notebooks.py --workspace-id <id> --token $(az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)
        """
    )
    
    parser.add_argument(
        "--workspace-id",
        required=True,
        help="Fabric workspace ID"
    )
    
    parser.add_argument(
        "--token",
        required=True,
        help="Azure access token"
    )
    
    parser.add_argument(
        "--notebook-dir",
        default=".",
        help="Directory containing notebook files (default: current directory)"
    )
    
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip notebooks that already exist in the workspace"
    )
    
    args = parser.parse_args()
    
    print("🚀 Starting Fabric notebook deployment...")
    
    # Initialize client
    client = FabricClient(args.workspace_id, args.token)
    
    # Get existing notebooks
    existing = {}
    try:
        existing_notebooks = client.get_notebooks()
        for nb in existing_notebooks:
            existing[nb.get("displayName")] = nb
        print(f"📋 Found {len(existing_notebooks)} existing notebooks in workspace")
    except Exception as e:
        print(f"⚠️  Warning: Could not list existing notebooks: {e}")
    
    # Deploy notebooks
    deployed = 0
    skipped = 0
    failed = 0
    
    for notebook_file in NOTEBOOKS:
        notebook_path = os.path.join(args.notebook_dir, notebook_file)
        display_name = get_notebook_display_name(notebook_file)
        
        print(f"\n📝 Processing '{display_name}'...")
        
        # Check if already exists
        if display_name in existing:
            if args.skip_existing:
                print(f"   ⏭️  Skipped (already exists)")
                skipped += 1
                continue
            else:
                print(f"   ⚠️  Notebook already exists, updating in place")
        
        try:
            # Load notebook content
            content = load_notebook_content(notebook_path)
            
            # Update existing notebook or create new one
            if display_name in existing:
                notebook_id = existing[display_name].get("id")
                response = client.update_notebook(notebook_id, content)
                print(f"   ✅ Updated successfully")
                if response.get("status") == "pending":
                    print(f"      Update status: pending")
                print(f"      Notebook ID: {notebook_id}")
            else:
                response = client.create_notebook(display_name, content)
                notebook_id = response.get("id")
                print(f"   ✅ Deployed successfully")
                print(f"      Notebook ID: {notebook_id}")
            deployed += 1
            
        except FileNotFoundError as e:
            print(f"   ✗ File not found: {e}")
            failed += 1
        except Exception as e:
            print(f"   ✗ Error: {e}")
            failed += 1
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Deployment Summary")
    print("=" * 50)
    print(f"✅ Deployed: {deployed}")
    print(f"⏭️  Skipped: {skipped}")
    print(f"❌ Failed: {failed}")
    print(f"📦 Total: {deployed + failed}")
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\n✨ Notebook deployment complete!")


if __name__ == "__main__":
    main()
