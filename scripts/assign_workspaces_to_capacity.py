#!/usr/bin/env python3
"""
Bulk-assign Fabric workspaces to a target capacity.

Reads workspace IDs from infra/workspace_ids.json (or another path) and assigns each
workspace to a specified capacity using Fabric REST API.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, List

from medallion.capacity import CapacityClient, load_workspace_ids, write_results
from medallion.utils import get_access_token_interactive

DEFAULT_WORKSPACE_IDS_FILE = "infra/workspace_ids.json"
DEFAULT_RESULTS_FILE = "infra/assignment_results.json"


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
    if len(sys.argv) > 1:
        print("This script uses the params file and does not accept command line arguments.")
        sys.exit(1)

    access_token = os.environ.get("FABRIC_ACCESS_TOKEN") or os.environ.get("AZURE_ACCESS_TOKEN")
    if not access_token:
        access_token = get_access_token_interactive()

    capacity_id = os.environ.get("FABRIC_CAPACITY_ID")
    if not capacity_id:
        print("❌ Set FABRIC_CAPACITY_ID before running this script.")
        sys.exit(1)

    try:
        workspaces = load_workspace_ids(DEFAULT_WORKSPACE_IDS_FILE)
    except (FileNotFoundError, ValueError) as error:
        print(f"❌ {error}")
        sys.exit(1)

    print("🚀 Starting workspace-to-capacity assignment...")
    print(f"   Capacity ID: {capacity_id}")
    print(f"   Input file: {DEFAULT_WORKSPACE_IDS_FILE}")
    print(f"   Workspaces found: {len(workspaces)}")
    print("   Dry run: False")

    client = CapacityClient(access_token)

    assigned = 0
    failed = 0
    details: List[dict] = []

    for row in workspaces:
        workspace_id = row["workspaceId"]
        workspace_name = row["workspaceName"]
        environment = row["environment"]

        print(f"\n🧭 [{environment}] {workspace_name} ({workspace_id})")

        status_code, endpoint, response_text = client.assign_workspace_to_capacity(
            workspace_id,
            capacity_id,
        )

        if status_code in (200, 201, 202, 204):
            assigned += 1
            print(f"   ✅ Assigned via {endpoint} (HTTP {status_code})")
            details.append(
                {
                    "environment": environment,
                    "workspaceName": workspace_name,
                    "workspaceId": workspace_id,
                    "capacityId": capacity_id,
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
                    "capacityId": capacity_id,
                    "status": "failed",
                    "httpStatus": status_code,
                    "endpoint": endpoint,
                    "response": response_text,
                }
            )

    result_payload = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "capacityId": capacity_id,
        "inputFile": DEFAULT_WORKSPACE_IDS_FILE,
        "dryRun": False,
        "summary": {
            "total": len(workspaces),
            "assigned": assigned,
            "failed": failed,
        },
        "details": details,
    }
    write_results(DEFAULT_RESULTS_FILE, result_payload)

    print("\n" + "=" * 72)
    print("📊 Assignment Summary")
    print("=" * 72)
    print(f"Total: {len(workspaces)}")
    print(f"Assigned: {assigned}")
    print(f"Failed: {failed}")
    print(f"Results file: {DEFAULT_RESULTS_FILE}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
