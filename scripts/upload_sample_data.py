#!/usr/bin/env python3
"""
Upload local data files to a Fabric Lakehouse Files/ section via the OneLake DFS API.

Usage:
    python scripts/upload_sample_data.py --token "$FABRIC_TOKEN"

    # Target a specific environment and lakehouse layer:
    python scripts/upload_sample_data.py --token "$FABRIC_TOKEN" --env dev --layer bronze

    # Override the local file and remote destination path:
    python scripts/upload_sample_data.py --token "$FABRIC_TOKEN" \\
        --file data/sample_raw_sales.csv \\
        --remote-path raw/sample_raw_sales.csv

Defaults:
    --env        dev
    --layer      bronze
    --file       data/sample_raw_sales.csv
    --remote-path raw/sample_raw_sales.csv   (inside the lakehouse Files/ root)
    --workspace-ids  infra/workspace_ids.json
"""

import argparse
import json
import os
import subprocess
import sys

import requests

ONELAKE_DFS_BASE = "https://onelake.dfs.fabric.microsoft.com"
ONELAKE_STORAGE_RESOURCE = "https://storage.azure.com"


def get_onelake_token() -> str:
    """Fetch a token scoped to the OneLake storage resource via Azure CLI."""
    try:
        result = subprocess.run(
            ["az", "account", "get-access-token", "--resource", ONELAKE_STORAGE_RESOURCE],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)["accessToken"]
    except FileNotFoundError:
        print("❌ Azure CLI not found — pass --onelake-token explicitly.")
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        print(f"❌ Failed to get OneLake token via az CLI: {exc.stderr.strip()}")
        print("   Run 'az login' first, or pass --onelake-token explicitly.")
        sys.exit(1)


def load_workspace_ids(path: str) -> dict:
    if not os.path.exists(path):
        print(f"❌ workspace_ids file not found: {path}")
        print(
            "   Run deploy_medallion_workspaces.py first to generate it, "
            "or pass --workspace-id and --lakehouse-id directly."
        )
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def find_lakehouse(workspace_ids: dict, env: str, layer: str):
    for ws in workspace_ids.get("workspaces", []):
        if ws.get("environment") == env:
            for lh in ws.get("lakehouses", []):
                if lh.get("medallionLayer") == layer:
                    return ws["workspaceId"], lh["id"], lh["name"]
    return None, None, None


def upload_file(
    onelake_token: str,
    workspace_id: str,
    lakehouse_id: str,
    local_path: str,
    remote_path: str,
) -> None:
    """Upload a file to OneLake using the ADLS Gen2 DFS protocol (create → append → flush)."""
    headers = {"Authorization": f"Bearer {onelake_token}"}

    with open(local_path, "rb") as fh:
        data = fh.read()

    file_size = len(data)
    dfs_url = f"{ONELAKE_DFS_BASE}/{workspace_id}/{lakehouse_id}/Files/{remote_path}"

    # Step 1 — create an empty file resource
    r = requests.put(dfs_url, headers=headers, params={"resource": "file"}, timeout=30)
    if r.status_code not in (200, 201):
        print(f"   API Response (create): {r.status_code}")
        print(f"   {r.text}")
        r.raise_for_status()

    # Step 2 — append the data at position 0
    append_headers = {**headers, "Content-Type": "application/octet-stream"}
    r = requests.patch(
        dfs_url,
        headers=append_headers,
        params={"action": "append", "position": "0"},
        data=data,
        timeout=60,
    )
    if r.status_code not in (200, 202):
        print(f"   API Response (append): {r.status_code}")
        print(f"   {r.text}")
        r.raise_for_status()

    # Step 3 — flush (commit) the file
    r = requests.patch(
        dfs_url,
        headers=headers,
        params={"action": "flush", "position": str(file_size)},
        timeout=30,
    )
    if r.status_code not in (200, 202):
        print(f"   API Response (flush): {r.status_code}")
        print(f"   {r.text}")
        r.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload a local file to a Fabric Lakehouse via OneLake DFS API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--token", required=True, help="Fabric Bearer access token (https://api.fabric.microsoft.com audience)")
    parser.add_argument(
        "--onelake-token",
        default=None,
        help=(
            "Bearer token scoped to https://storage.azure.com for OneLake DFS uploads. "
            "If omitted, fetched automatically via 'az account get-access-token'."
        ),
    )
    parser.add_argument(
        "--env",
        default="dev",
        help="Target environment (default: dev)",
    )
    parser.add_argument(
        "--layer",
        default="bronze",
        help="Target medallion lakehouse layer (default: bronze)",
    )
    parser.add_argument(
        "--file",
        default="data/sample_raw_sales.csv",
        help="Local file to upload (default: data/sample_raw_sales.csv)",
    )
    parser.add_argument(
        "--remote-path",
        default="raw/sample_raw_sales.csv",
        help="Destination path inside lakehouse Files/ (default: raw/sample_raw_sales.csv)",
    )
    parser.add_argument(
        "--workspace-ids",
        default="infra/workspace_ids.json",
        help="Path to workspace_ids.json (default: infra/workspace_ids.json)",
    )
    # Direct-ID overrides (bypass workspace_ids.json lookup)
    parser.add_argument("--workspace-id", help="Override: Fabric workspace GUID")
    parser.add_argument("--lakehouse-id", help="Override: Fabric lakehouse GUID")

    args = parser.parse_args()

    local_path = args.file
    if not os.path.exists(local_path):
        print(f"❌ Local file not found: {local_path}")
        sys.exit(1)

    if args.workspace_id and args.lakehouse_id:
        workspace_id = args.workspace_id
        lakehouse_id = args.lakehouse_id
        lakehouse_name = f"{args.layer}_lakehouse"
    else:
        workspace_ids = load_workspace_ids(args.workspace_ids)
        workspace_id, lakehouse_id, lakehouse_name = find_lakehouse(
            workspace_ids, args.env, args.layer
        )
        if not workspace_id:
            print(
                f"❌ No lakehouse found for env='{args.env}', layer='{args.layer}' "
                f"in {args.workspace_ids}"
            )
            sys.exit(1)

    remote_path = args.remote_path.lstrip("/")
    file_size = os.path.getsize(local_path)

    onelake_token = args.onelake_token or get_onelake_token()

    print(f"📤 Uploading '{local_path}' ({file_size} bytes) →")
    print(f"   Workspace : {workspace_id}")
    print(f"   Lakehouse : {lakehouse_name} ({lakehouse_id})")
    print(f"   Destination: Files/{remote_path}")

    try:
        upload_file(onelake_token, workspace_id, lakehouse_id, local_path, remote_path)
        print("✅ Upload complete")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"❌ Upload failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
