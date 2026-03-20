#!/usr/bin/env python3
"""
Bulk-assign Fabric workspaces to a target capacity.

Reads workspace IDs from infra/workspace_ids.json (or another path) and assigns each
workspace to a specified capacity using Fabric REST API.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import requests


FABRIC_API_BASE_URL = "https://api.fabric.microsoft.com/v1"
DEFAULT_WORKSPACE_IDS_FILE = "infra/workspace_ids.json"
DEFAULT_RESULTS_FILE = "infra/workspace_capacity_assignment_results.json"


class FabricClient:
    """Client for Fabric capacity assignment operations."""

    def __init__(self, access_token: str):
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def assign_workspace_to_capacity(self, workspace_id: str, capacity_id: str) -> Tuple[int, str, str]:
        """
        Assign a workspace to a Fabric capacity.

        Returns:
            (status_code, endpoint_used, response_text)
        """
        payload = {"capacityId": capacity_id}

        # Keep more than one endpoint pattern to handle tenant/API variations.
        endpoint_templates = [
            f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/assignToCapacity",
            f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/capacityAssignments",
        ]

        last_status = 0
        last_text = ""
        last_endpoint = endpoint_templates[0]

        for endpoint in endpoint_templates:
            response = requests.post(endpoint, json=payload, headers=self.headers)

            if response.status_code in (200, 201, 202, 204):
                return response.status_code, endpoint, response.text

            # If endpoint does not exist in this API version, try fallback endpoint.
            if response.status_code in (404, 405):
                last_status = response.status_code
                last_text = response.text
                last_endpoint = endpoint
                continue

            # For permission/validation errors, stop immediately.
            return response.status_code, endpoint, response.text

        return last_status, last_endpoint, last_text


def get_access_token_interactive() -> str:
    """Get Fabric API access token from Azure CLI."""
    print("Attempting to get access token via Azure CLI...")
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
        print("❌ Azure CLI not found. Install Azure CLI or pass --token.")
        sys.exit(1)
    except subprocess.CalledProcessError:
        print("❌ Failed to get access token. Run 'az login' first.")
        sys.exit(1)


def load_workspace_ids(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Workspace IDs file not found: {path}")

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("Workspace IDs file must be a JSON object.")

    workspaces = data.get("workspaces", [])
    if not isinstance(workspaces, list):
        raise ValueError("The 'workspaces' property must be a JSON array.")

    normalized = []
    for row in workspaces:
        if not isinstance(row, dict):
            continue

        workspace_id = row.get("workspaceId")
        if not workspace_id:
            continue

        normalized.append(
            {
                "environment": row.get("environment", row.get("layer", "unknown")),
                "workspaceName": row.get("workspaceName", "unknown"),
                "workspaceId": workspace_id,
            }
        )

    if not normalized:
        raise ValueError("No workspace IDs found under the 'workspaces' array.")

    return normalized


def write_results(path: str, payload: dict) -> None:
    output_dir = os.path.dirname(path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk-assign Fabric workspaces to a target capacity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/assign_workspaces_to_capacity.py --interactive --capacity-id <capacityId>\n"
            "  python scripts/assign_workspaces_to_capacity.py --token <token> --capacity-id <capacityId> --workspace-ids-file infra/workspace_ids.json"
        ),
    )

    parser.add_argument(
        "--token",
        help="Azure access token for https://api.fabric.microsoft.com",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Get token using Azure CLI",
    )
    parser.add_argument(
        "--capacity-id",
        required=True,
        help="Target Fabric capacity ID",
    )
    parser.add_argument(
        "--workspace-ids-file",
        default=DEFAULT_WORKSPACE_IDS_FILE,
        help=f"Path to workspace IDs input JSON (default: {DEFAULT_WORKSPACE_IDS_FILE})",
    )
    parser.add_argument(
        "--results-file",
        default=DEFAULT_RESULTS_FILE,
        help=f"Path for assignment results JSON (default: {DEFAULT_RESULTS_FILE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned assignments without making API calls",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first assignment failure",
    )

    args = parser.parse_args()

    if args.interactive:
        access_token = get_access_token_interactive()
    elif args.token:
        access_token = args.token
    else:
        print("❌ Provide --token or use --interactive")
        sys.exit(1)

    try:
        workspaces = load_workspace_ids(args.workspace_ids_file)
    except (FileNotFoundError, ValueError) as error:
        print(f"❌ {error}")
        sys.exit(1)

    print("🚀 Starting workspace-to-capacity assignment...")
    print(f"   Capacity ID: {args.capacity_id}")
    print(f"   Input file: {args.workspace_ids_file}")
    print(f"   Workspaces found: {len(workspaces)}")
    print(f"   Dry run: {args.dry_run}")

    client = FabricClient(access_token)

    assigned = 0
    failed = 0
    details: List[dict] = []

    for row in workspaces:
        workspace_id = row["workspaceId"]
        workspace_name = row["workspaceName"]
        environment = row["environment"]

        print(f"\n🧭 [{environment}] {workspace_name} ({workspace_id})")

        if args.dry_run:
            print("   📝 Dry run only; no API call made")
            details.append(
                {
                    "environment": environment,
                    "workspaceName": workspace_name,
                    "workspaceId": workspace_id,
                    "capacityId": args.capacity_id,
                    "status": "dry-run",
                }
            )
            continue

        status_code, endpoint, response_text = client.assign_workspace_to_capacity(
            workspace_id,
            args.capacity_id,
        )

        if status_code in (200, 201, 202, 204):
            assigned += 1
            print(f"   ✅ Assigned via {endpoint} (HTTP {status_code})")
            details.append(
                {
                    "environment": environment,
                    "workspaceName": workspace_name,
                    "workspaceId": workspace_id,
                    "capacityId": args.capacity_id,
                    "status": "assigned",
                    "httpStatus": status_code,
                    "endpoint": endpoint,
                }
            )
        else:
            failed += 1
            print(f"   ❌ Failed (HTTP {status_code}) via {endpoint}")
            if response_text:
                print(f"      Response: {response_text[:500]}")
            details.append(
                {
                    "environment": environment,
                    "workspaceName": workspace_name,
                    "workspaceId": workspace_id,
                    "capacityId": args.capacity_id,
                    "status": "failed",
                    "httpStatus": status_code,
                    "endpoint": endpoint,
                    "response": response_text,
                }
            )

            if args.fail_fast:
                break

    result_payload = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "capacityId": args.capacity_id,
        "inputFile": args.workspace_ids_file,
        "dryRun": args.dry_run,
        "summary": {
            "total": len(workspaces),
            "assigned": assigned,
            "failed": failed,
        },
        "details": details,
    }
    write_results(args.results_file, result_payload)

    print("\n" + "=" * 72)
    print("📊 Assignment Summary")
    print("=" * 72)
    print(f"Total: {len(workspaces)}")
    print(f"Assigned: {assigned}")
    print(f"Failed: {failed}")
    print(f"Results file: {args.results_file}")

    if failed > 0 and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
