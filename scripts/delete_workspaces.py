#!/usr/bin/env python3
"""
Delete Fabric workspaces using the REST API.

This script deletes workspaces from Microsoft Fabric by workspace ID.
Workspace IDs can be provided directly or loaded from infra/workspace_ids.json.

Usage:
    # Delete by ID
    python scripts/delete_workspaces.py --token <token> \\
        "12345678-1234-1234-1234-123456789012" "87654321-4321-4321-4321-210987654321"
    
    # Delete by workspace name from workspace_ids.json
    python scripts/delete_workspaces.py --token <token> \\
        --from-file infra/workspace_ids.json "Road4_Bronze_Dev" "Road4_Silver"
    
    # Delete specific environments from file
    python scripts/delete_workspaces.py --token <token> \\
        --from-file infra/workspace_ids.json --environments Dev,Staging
    
    # Dry run (show what would be deleted)
    python scripts/delete_workspaces.py --token <token> --dry-run \\
        "12345678-1234-1234-1234-123456789012"
    
    # Get token from Azure CLI
    python scripts/delete_workspaces.py \\
        --interactive \\
        --from-file infra/workspace_ids.json "Road4_Bronze_Dev"
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

import requests

FABRIC_API_BASE_URL = "https://api.fabric.microsoft.com/v1"


def get_access_token_interactive() -> str:
    """Get access token from Azure CLI."""
    print("🔐 Attempting to get access token via Azure CLI...")
    try:
        result = subprocess.run(
            [
                "az",
                "account",
                "get-access-token",
                "--resource",
                "https://api.fabric.microsoft.com",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        token_data = json.loads(result.stdout)
        return token_data["accessToken"]
    except FileNotFoundError:
        print("❌ Azure CLI not found. Install Azure CLI or pass --token directly.")
        sys.exit(1)
    except subprocess.CalledProcessError:
        print("❌ Failed to get access token. Run 'az login' first.")
        sys.exit(1)


def load_workspace_ids_from_file(file_path: str) -> Dict[str, str]:
    """Load workspace names and IDs from workspace_ids.json."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Workspace IDs file not found: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Build a map of workspace names to IDs
    workspace_map = {}
    for ws in data.get('workspaces', []):
        workspace_id = ws.get('workspaceId')
        workspace_name = ws.get('workspaceName')
        if workspace_id and workspace_name:
            workspace_map[workspace_name] = workspace_id
    
    return workspace_map


def find_workspace_ids(
    identifiers: List[str],
    workspace_id_map: Optional[Dict[str, str]] = None
) -> Tuple[List[str], List[str]]:
    """
    Resolve identifiers to workspace IDs.
    Identifiers can be UUIDs or workspace names (if map is provided).
    
    Returns:
        (resolved_ids, unresolved_identifiers)
    """
    resolved_ids = []
    unresolved = []
    
    for identifier in identifiers:
        # Check if it's a UUID (basic check)
        if len(identifier) == 36 and identifier.count('-') == 4:
            resolved_ids.append(identifier)
        elif workspace_id_map and identifier in workspace_id_map:
            resolved_ids.append(workspace_id_map[identifier])
        else:
            unresolved.append(identifier)
    
    return resolved_ids, unresolved


def delete_workspace(access_token: str, workspace_id: str) -> Tuple[bool, str]:
    """
    Delete a workspace by ID.
    
    Returns:
        (success, message)
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    url = f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}"
    
    try:
        response = requests.delete(url, headers=headers)
        
        if response.status_code in (200, 204):
            return True, f"HTTP {response.status_code}"
        elif response.status_code == 404:
            return False, f"Workspace not found (HTTP {response.status_code})"
        else:
            return False, f"HTTP {response.status_code}: {response.text[:100]}"
    except requests.RequestException as e:
        return False, str(e)


def get_workspace_info(access_token: str, workspace_id: str) -> Optional[Dict]:
    """Get workspace details to display name."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    url = f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}"
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    
    return None


def list_all_workspaces(access_token: str) -> List[Dict]:
    """Fetch all workspaces from Fabric."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    url = f"{FABRIC_API_BASE_URL}/workspaces"
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get('value', [])
    except Exception as e:
        print(f"❌ Error fetching workspaces: {e}")
    
    return []


def search_workspaces(access_token: str, search_term: str) -> List[Dict]:
    """Search workspaces by name (case-insensitive partial match)."""
    all_workspaces = list_all_workspaces(access_token)
    search_lower = search_term.lower()
    return [ws for ws in all_workspaces if search_lower in ws.get('displayName', '').lower()]


def main():
    parser = argparse.ArgumentParser(
        description="Delete Fabric workspaces or list/search for them",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all workspaces
  python scripts/delete_workspaces.py --token <token> --list
  
  # Search for workspaces by name
  python scripts/delete_workspaces.py --token <token> --search "Bronze"
  
  # Delete by UUID
  python scripts/delete_workspaces.py --token <token> \\
      "12345678-1234-1234-1234-123456789012"
  
  # Delete by name from workspace_ids.json
  python scripts/delete_workspaces.py --token <token> \\
      --from-file infra/workspace_ids.json "Road4_Bronze_Dev"
  
  # Delete specific environments
  python scripts/delete_workspaces.py --token <token> \\
      --from-file infra/workspace_ids.json --environments Dev,Staging
  
  # Dry run
  python scripts/delete_workspaces.py --token <token> --dry-run \\
      "12345678-1234-1234-1234-123456789012"
  
  # Interactive (get token from Azure CLI)
  python scripts/delete_workspaces.py --interactive --list
        """
    )
    
    parser.add_argument(
        "--token",
        help="Azure access token for Fabric API"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Get token via Azure CLI (run 'az login' first)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all workspaces in Fabric"
    )
    parser.add_argument(
        "--search",
        metavar="SEARCH_TERM",
        help="Search workspaces by name (case-insensitive)"
    )
    parser.add_argument(
        "--from-file",
        help="Load workspace IDs from JSON file (e.g., infra/workspace_ids.json)"
    )
    parser.add_argument(
        "--environments",
        help="Filter by environments (comma-separated: Dev,Staging,Prod,Feature)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without making API calls"
    )
    parser.add_argument(
        "workspace_identifiers",
        nargs='*',
        help="Workspace IDs (UUIDs) or names to delete"
    )
    
    args = parser.parse_args()
    
    # Get access token
    if args.interactive:
        access_token = get_access_token_interactive()
    elif args.token:
        access_token = args.token
    else:
        print("❌ Provide --token or use --interactive")
        sys.exit(1)
    
    # Handle --list
    if args.list:
        print("📋 Fetching all workspaces from Fabric...")
        workspaces = list_all_workspaces(access_token)
        
        if not workspaces:
            print("⚠️  No workspaces found")
            return
        
        print(f"\n✅ Found {len(workspaces)} workspace(s):\n")
        print(f"{'Name':<40} {'Workspace ID':<40} {'Type':<15}")
        print("-" * 100)
        for ws in sorted(workspaces, key=lambda x: x.get('displayName', '')):
            name = ws.get('displayName', 'N/A')[:40]
            ws_id = ws.get('id', 'N/A')
            ws_type = ws.get('type', 'N/A')
            print(f"{name:<40} {ws_id:<40} {ws_type:<15}")
        return
    
    # Handle --search
    if args.search:
        print(f"🔍 Searching for workspaces matching '{args.search}'...")
        workspaces = search_workspaces(access_token, args.search)
        
        if not workspaces:
            print(f"⚠️  No workspaces found matching '{args.search}'")
            return
        
        print(f"\n✅ Found {len(workspaces)} workspace(s):\n")
        print(f"{'Name':<40} {'Workspace ID':<40} {'Type':<15}")
        print("-" * 100)
        for ws in sorted(workspaces, key=lambda x: x.get('displayName', '')):
            name = ws.get('displayName', 'N/A')[:40]
            ws_id = ws.get('id', 'N/A')
            ws_type = ws.get('type', 'N/A')
            print(f"{name:<40} {ws_id:<40} {ws_type:<15}")
        return
    
    # Load workspace mappings if --from-file is provided
    workspace_map = {}
    workspaces_to_delete = []
    
    if args.from_file:
        if not os.path.exists(args.from_file):
            print(f"❌ File not found: {args.from_file}")
            sys.exit(1)
        
        try:
            with open(args.from_file, 'r', encoding='utf-8') as f:
                file_data = json.load(f)
            
            # Filter by environment if specified
            environments = []
            if args.environments:
                environments = [e.strip().lower() for e in args.environments.split(',')]
            
            for ws in file_data.get('workspaces', []):
                workspace_id = ws.get('workspaceId')
                workspace_name = ws.get('workspaceName')
                environment = ws.get('environment', '').lower()
                
                if workspace_id and workspace_name:
                    workspace_map[workspace_name] = workspace_id
                    
                    # If environments filter is set, only include matching ones
                    if environments and environment in environments:
                        workspaces_to_delete.append((workspace_id, workspace_name, environment))
                    # If no environments filter and no specific identifiers, skip (require explicit names)
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing JSON: {e}")
            sys.exit(1)
    
    # Process workspace identifiers from command line
    if args.workspace_identifiers:
        resolved_ids, unresolved = find_workspace_ids(args.workspace_identifiers, workspace_map)
        
        if unresolved:
            print(f"⚠️  Could not resolve: {', '.join(unresolved)}")
        
        # Add resolved IDs
        for workspace_id in resolved_ids:
            workspace_name = workspace_map.get(workspace_id, "N/A")
            # Find environment from file data if available
            environment = "unknown"
            if args.from_file:
                with open(args.from_file, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    for ws in file_data.get('workspaces', []):
                        if ws.get('workspaceId') == workspace_id:
                            environment = ws.get('environment', 'unknown')
                            break
            workspaces_to_delete.append((workspace_id, workspace_name, environment))
    
    if not workspaces_to_delete:
        print("⚠️  No workspaces to delete.")
        sys.exit(0)
    
    # Display what will be deleted
    print(f"\n🗑️  Workspace(s) to delete: {len(workspaces_to_delete)}")
    print("-" * 80)
    for workspace_id, workspace_name, environment in workspaces_to_delete:
        print(f"  {workspace_name:30} [{environment:10}] {workspace_id}")
    print("-" * 80)
    
    if args.dry_run:
        print("\n🏃 Dry run mode: no workspaces deleted")
        sys.exit(0)
    
    # Confirm deletion
    response = input("\n⚠️  This action cannot be undone. Continue? (type 'yes' to confirm): ")
    if response.lower() != 'yes':
        print("❌ Deletion cancelled")
        sys.exit(0)
    
    # Delete workspaces
    print("\n🔄 Deleting workspaces...")
    deleted = 0
    failed = 0
    
    for workspace_id, workspace_name, environment in workspaces_to_delete:
        success, message = delete_workspace(access_token, workspace_id)
        if success:
            deleted += 1
            print(f"  ✅ {workspace_name:30} {message}")
        else:
            failed += 1
            print(f"  ❌ {workspace_name:30} {message}")
    
    print("\n" + "=" * 80)
    print(f"✅ Deleted: {deleted}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total: {deleted + failed}")
    
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
