#!/usr/bin/env python3
"""
Create a 4-environment Fabric setup with medallion lakehouses and notebooks.

Default workspaces:
- dev
- prod
- feature
- staging

For each workspace this script:
1. Creates (or reuses) the Fabric workspace
2. Optionally assigns the workspace to a Fabric capacity
3. Creates (or reuses) the medallion lakehouses in that workspace
4. Deploys notebooks to that workspace
"""

import argparse
import base64
import copy
import json
import os
import subprocess
from datetime import datetime, timezone
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

import requests


FABRIC_API_BASE_URL = "https://api.fabric.microsoft.com/v1"
DEFAULT_ENVIRONMENTS = ["dev", "prod", "feature", "staging"]
DEFAULT_MEDALLION_LAKEHOUSES = ["raw", "bronze", "silver", "gold"]
DEFAULT_NOTEBOOKS = [
    "01_ingest_raw_sales_python.ipynb",
    "01_ingest_raw_sales.ipynb",
    "02_clean_sales_data.ipynb",
    "03_curate_sales_mart.ipynb",
]
DEFAULT_PIPELINES_BY_LAYER = {
    "bronze": ["bronze/pipelines/bronze_ingest_pipeline.json"],
    "silver": ["silver/pipelines/silver_transform_pipeline.json"],
    "gold": ["gold/pipelines/gold_curated_pipeline.json"],
}
DEFAULT_PARAMS_FILE = "infra/medallion_workspace_params.json"
DEFAULT_WORKSPACE_IDS_OUTPUT = "infra/workspace_ids.json"
PLATFORM_SCHEMA_URL = (
    "https://developer.microsoft.com/json-schemas/"
    "fabric/gitIntegration/platformProperties/2.0.0/schema.json"
)


class FabricClient:
    """Minimal Fabric API client for multi-workspace deployment."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def list_workspaces(self) -> List[dict]:
        url = f"{FABRIC_API_BASE_URL}/workspaces"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json().get("value", [])

    def get_workspace_by_name(self, display_name: str) -> Optional[dict]:
        for workspace in self.list_workspaces():
            if workspace.get("displayName") == display_name:
                return workspace
        return None

    def create_workspace(
        self,
        display_name: str,
        description: Optional[str] = None,
        capacity_id: Optional[str] = None,
    ) -> None:
        url = f"{FABRIC_API_BASE_URL}/workspaces"
        payload = {"displayName": display_name}

        if description:
            payload["description"] = description
        if capacity_id:
            payload["capacityId"] = capacity_id

        response = requests.post(url, json=payload, headers=self.headers)

        if response.status_code not in (200, 201, 202):
            print(f"   API Response: {response.status_code}")
            print(f"   Error: {response.text}")

        response.raise_for_status()

    def assign_workspace_to_capacity(self, workspace_id: str, capacity_id: str) -> dict:
        """Assign an existing workspace to a Fabric capacity."""
        payload = {"capacityId": capacity_id}
        endpoints = [
            f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/assignToCapacity",
            f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/capacityAssignments",
        ]

        last_status = None
        last_error = ""

        for endpoint in endpoints:
            response = requests.post(endpoint, json=payload, headers=self.headers)

            if response.status_code in (200, 201, 202, 204):
                return {
                    "statusCode": response.status_code,
                    "endpoint": endpoint,
                }

            if response.status_code in (404, 405):
                last_status = response.status_code
                last_error = response.text
                continue

            response.raise_for_status()

        raise RuntimeError(
            "Unable to assign workspace to capacity. "
            f"Last status: {last_status}, response: {last_error}"
        )

    def get_or_create_workspace(
        self,
        display_name: str,
        description: Optional[str] = None,
        capacity_id: Optional[str] = None,
        wait_seconds: int = 90,
    ) -> dict:
        existing = self.get_workspace_by_name(display_name)
        if existing:
            return existing

        self.create_workspace(display_name, description=description, capacity_id=capacity_id)

        # Workspace creation can be asynchronous; poll until it is visible.
        end_time = time.time() + wait_seconds
        while time.time() < end_time:
            created = self.get_workspace_by_name(display_name)
            if created:
                return created
            time.sleep(3)

        raise TimeoutError(
            f"Workspace '{display_name}' was requested but not visible after {wait_seconds} seconds."
        )

    def list_lakehouses(self, workspace_id: str) -> List[dict]:
        url = f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/lakehouses"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json().get("value", [])

    def get_lakehouse_by_name(self, workspace_id: str, display_name: str) -> Optional[dict]:
        for lakehouse in self.list_lakehouses(workspace_id):
            if lakehouse.get("displayName") == display_name:
                return lakehouse
        return None

    def create_lakehouse(self, workspace_id: str, display_name: str) -> dict:
        url = f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/lakehouses"
        payload = {"displayName": display_name}

        response = requests.post(url, json=payload, headers=self.headers)
        if response.status_code not in (200, 201, 202):
            print(f"   API Response: {response.status_code}")
            print(f"   Error: {response.text}")
        response.raise_for_status()

        if response.status_code == 202:
            return {"id": "pending", "displayName": display_name, "status": "pending"}

        return response.json()

    def get_or_create_lakehouse(self, workspace_id: str, display_name: str) -> dict:
        existing = self.get_lakehouse_by_name(workspace_id, display_name)
        if existing:
            return existing

        created = self.create_lakehouse(workspace_id, display_name)

        # Handle async creation by checking name again.
        if created.get("id") == "pending":
            for _ in range(30):
                candidate = self.get_lakehouse_by_name(workspace_id, display_name)
                if candidate:
                    return candidate
                time.sleep(2)
            raise TimeoutError(f"Lakehouse '{display_name}' not visible after async creation.")

        return created

    def list_notebooks(self, workspace_id: str) -> List[dict]:
        url = f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/notebooks"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json().get("value", [])

    def list_pipelines(self, workspace_id: str) -> List[dict]:
        endpoints = [
            (
                f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/dataPipelines",
                None,
            ),
            (
                f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/items",
                {"type": "DataPipeline"},
            ),
        ]

        for url, params in endpoints:
            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code in (404, 405):
                continue
            response.raise_for_status()
            return response.json().get("value", [])

        return []

    def notebook_exists(self, workspace_id: str, display_name: str) -> bool:
        for notebook in self.list_notebooks(workspace_id):
            if notebook.get("displayName") == display_name:
                return True
        return False

    def get_notebook_id(self, workspace_id: str, display_name: str) -> Optional[str]:
        for notebook in self.list_notebooks(workspace_id):
            if notebook.get("displayName") == display_name:
                return notebook.get("id")
        return None

    def pipeline_exists(self, workspace_id: str, display_name: str) -> bool:
        for pipeline in self.list_pipelines(workspace_id):
            if pipeline.get("displayName") == display_name:
                return True
        return False

    def create_notebook(self, workspace_id: str, display_name: str, content: dict) -> dict:
        url = f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/notebooks"

        notebook_json = json.dumps(content).encode("utf-8")
        notebook_b64 = base64.b64encode(notebook_json).decode("utf-8")

        payload = {
            "displayName": display_name,
            "definition": {
                "format": "ipynb",
                "parts": [
                    {
                        "path": "notebook-content.ipynb",
                        "payloadType": "InlineBase64",
                        "payload": notebook_b64,
                    }
                ],
            },
        }

        response = requests.post(url, json=payload, headers=self.headers)

        if response.status_code not in (200, 201, 202):
            print(f"   API Response: {response.status_code}")
            print(f"   Error: {response.text}")

        if response.status_code == 400 and "ItemDisplayNameAlreadyInUse" in response.text:
            return {"id": display_name, "displayName": display_name, "status": "exists"}

        response.raise_for_status()

        if response.status_code == 202:
            return {"id": "pending", "displayName": display_name, "status": "pending"}

        return response.json()

    def create_pipeline(self, workspace_id: str, display_name: str, content: dict) -> dict:
        pipeline_definition = normalize_pipeline_definition(content)
        pipeline_json = json.dumps(pipeline_definition).encode("utf-8")
        pipeline_b64 = base64.b64encode(pipeline_json).decode("utf-8")
        platform_b64 = build_platform_payload_b64(display_name, "DataPipeline")

        payload = {
            "displayName": display_name,
            "definition": {
                "parts": [
                    {
                        "path": "pipeline-content.json",
                        "payloadType": "InlineBase64",
                        "payload": pipeline_b64,
                    },
                    {
                        "path": ".platform",
                        "payloadType": "InlineBase64",
                        "payload": platform_b64,
                    }
                ],
            },
        }

        endpoints = [f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/dataPipelines"]

        last_status = None
        last_error = ""

        for url in endpoints:
            response = requests.post(url, json=payload, headers=self.headers)
            if response.status_code in (404, 405):
                last_status = response.status_code
                last_error = response.text
                continue
            if response.status_code == 400 and "ItemDisplayNameAlreadyInUse" in response.text:
                return {"id": display_name, "displayName": display_name, "status": "exists"}
            if response.status_code not in (200, 201, 202):
                print(f"   API Response: {response.status_code}")
                print(f"   Error: {response.text}")
            response.raise_for_status()

            if response.status_code == 202:
                return {"id": "pending", "displayName": display_name, "status": "pending"}

            return response.json()

        raise RuntimeError(
            "Unable to create pipeline with available Fabric endpoints. "
            f"Last status: {last_status}, response: {last_error}"
        )

    def create_pipeline_shell(self, workspace_id: str, display_name: str, description: str = "") -> dict:
        url = f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/items"
        payload = {
            "displayName": display_name,
            "description": description,
            "type": "DataPipeline",
        }

        response = requests.post(url, json=payload, headers=self.headers)

        if response.status_code == 400 and "ItemDisplayNameAlreadyInUse" in response.text:
            return {"id": display_name, "displayName": display_name, "status": "exists"}

        if response.status_code not in (200, 201, 202):
            print(f"   API Response: {response.status_code}")
            print(f"   Error: {response.text}")

        response.raise_for_status()

        if response.status_code == 202:
            return {"id": "pending", "displayName": display_name, "status": "pending"}

        return response.json()


def get_access_token_interactive() -> str:
    """Get a Fabric token from Azure CLI."""
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


def choose_existing_notebooks(notebook_dir: str, candidates: List[str]) -> List[str]:
    """Return candidate notebook filenames that exist in notebook_dir."""
    found = []
    for filename in candidates:
        if os.path.exists(os.path.join(notebook_dir, filename)):
            found.append(filename)
    return found


def load_notebook_content(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_json_content(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def build_platform_payload_b64(display_name: str, item_type: str) -> str:
    platform = {
        "$schema": PLATFORM_SCHEMA_URL,
        "metadata": {
            "type": item_type,
            "displayName": display_name,
        },
        "config": {
            "version": "2.0",
            "logicalId": str(uuid4()),
        },
    }
    return base64.b64encode(json.dumps(platform).encode("utf-8")).decode("utf-8")


def normalize_pipeline_definition(content: dict) -> dict:
    if "properties" in content:
        return content

    properties = {"activities": []}
    if content.get("description"):
        properties["description"] = content["description"]

    for activity in content.get("activities", []):
        normalized_activity = dict(activity)
        normalized_activity.setdefault("dependsOn", [])
        properties["activities"].append(normalized_activity)

    return {"properties": properties}


def resolve_notebook_references(
    content: dict,
    workspace_id: str,
    notebook_id_map: Dict[str, str],
    client: "FabricClient",
) -> dict:
    """Replace notebookName placeholders in TridentNotebook activities with real Fabric IDs."""
    content = copy.deepcopy(content)
    if "properties" in content:
        activities = content["properties"].get("activities", [])
    else:
        activities = content.get("activities", [])

    for activity in activities:
        if activity.get("type") == "TridentNotebook":
            type_props = activity.setdefault("typeProperties", {})
            notebook_name = type_props.pop("notebookName", None)
            if notebook_name and "notebookId" not in type_props:
                nb_id = notebook_id_map.get(notebook_name) or client.get_notebook_id(
                    workspace_id, notebook_name
                )
                if nb_id:
                    type_props["notebookId"] = nb_id
                    type_props["workspaceId"] = workspace_id
                else:
                    print(
                        f"   ⚠️ Could not resolve notebook ID for '{notebook_name}', "
                        "pipeline activity may fail at runtime"
                    )
                    type_props["notebookName"] = notebook_name  # restore placeholder
    return content


def notebook_display_name(notebook_filename: str) -> str:
    return Path(notebook_filename).stem


def pipeline_display_name(file_path: str, content: dict) -> str:
    return content.get("name", Path(file_path).stem)


def choose_existing_files(base_dir: str, candidates: List[str]) -> List[str]:
    found = []
    for relative_path in candidates:
        if os.path.exists(os.path.join(base_dir, relative_path)):
            found.append(relative_path)
    return found


def parse_csv_values(raw_values: str, label: str) -> List[str]:
    values = [value.strip().lower() for value in raw_values.split(",") if value.strip()]
    if not values:
        raise ValueError(f"At least one {label} value must be provided.")
    return values


def load_params_file(params_file: str) -> dict:
    if not os.path.exists(params_file):
        return {}

    with open(params_file, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("Parameter file content must be a JSON object.")

    return data


def resolve_workspace_name(environment: str, prefix: str, workspace_names: dict) -> str:
    explicit_name = workspace_names.get(environment)
    if explicit_name:
        return explicit_name
    return f"{prefix}-{environment}"


def resolve_lakehouse_name(lakehouse_key: str, lakehouse_suffix: str, lakehouse_names: dict) -> str:
    explicit_name = lakehouse_names.get(lakehouse_key)
    if explicit_name:
        return explicit_name
    return f"{lakehouse_key}_{lakehouse_suffix}"


def write_workspace_ids(output_path: str, payload: dict) -> None:
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create Fabric environment workspaces with medallion lakehouses + notebooks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/deploy_medallion_workspaces.py --interactive\n"
            "  python scripts/deploy_medallion_workspaces.py --interactive --workspace dev\n"
            "  python scripts/deploy_medallion_workspaces.py --interactive --workspace prod\n"
            "  python scripts/deploy_medallion_workspaces.py --interactive --workspace staging\n"
            "  python scripts/deploy_medallion_workspaces.py --interactive --workspace feature\n"
            "  python scripts/deploy_medallion_workspaces.py --interactive --workspace all\n"
            "  python scripts/deploy_medallion_workspaces.py --token <token> --params-file infra/medallion_workspace_params.json\n"
            "  python scripts/deploy_medallion_workspaces.py --environments dev,prod,feature,staging --capacity-id <id>"
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
        "--prefix",
        default=None,
        help="Workspace naming prefix (default: medallion)",
    )
    parser.add_argument(
        "--environments",
        default=None,
        help="Comma-separated workspaces to create (default: dev,prod,feature,staging)",
    )
    parser.add_argument(
        "--workspace",
        choices=["dev", "prod", "staging", "feature", "all"],
        default="all",
        help=(
            "Quick workspace selector. Use 'dev' or 'prod' to deploy to one workspace, "
            "or 'all' to deploy all environments from --environments/params file (default: all)."
        ),
    )
    parser.add_argument(
        "--medallion-lakehouses",
        default=None,
        help="Comma-separated medallion lakehouses to create per workspace (default: raw,bronze,silver,gold)",
    )
    parser.add_argument(
        "--lakehouse-suffix",
        default=None,
        help="Suffix for each lakehouse display name (default: lakehouse)",
    )
    parser.add_argument(
        "--notebook-dir",
        default=None,
        help="Directory containing notebook files (default: Medallion)",
    )
    parser.add_argument(
        "--capacity-id",
        help="Optional Fabric capacity ID for workspace creation",
    )
    parser.add_argument(
        "--workspace-description",
        default=None,
        help="Description set on created workspaces",
    )
    parser.add_argument(
        "--params-file",
        default=DEFAULT_PARAMS_FILE,
        help=f"Path to JSON parameter file (default: {DEFAULT_PARAMS_FILE})",
    )
    parser.add_argument(
        "--workspace-ids-output",
        default=None,
        help=f"Output JSON path for created workspace IDs (default: {DEFAULT_WORKSPACE_IDS_OUTPUT})",
    )
    parser.add_argument(
        "--skip-existing-notebooks",
        action="store_true",
        help="Skip notebook deployment when the notebook already exists",
    )
    parser.add_argument(
        "--skip-existing-pipelines",
        action="store_true",
        help="Skip pipeline deployment when the pipeline already exists",
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
        params = load_params_file(args.params_file)
    except ValueError as error:
        print(f"❌ Invalid parameter file: {error}")
        sys.exit(1)

    prefix = args.prefix if args.prefix is not None else params.get("prefix", "medallion")
    environments_raw = (
        args.environments
        if args.environments is not None
        else params.get("environments", ",".join(DEFAULT_ENVIRONMENTS))
    )
    medallion_lakehouses_raw = (
        args.medallion_lakehouses
        if args.medallion_lakehouses is not None
        else params.get("medallion_lakehouses", ",".join(DEFAULT_MEDALLION_LAKEHOUSES))
    )
    lakehouse_suffix = (
        args.lakehouse_suffix
        if args.lakehouse_suffix is not None
        else params.get("lakehouse_suffix", "lakehouse")
    )
    notebook_dir = args.notebook_dir if args.notebook_dir is not None else params.get("notebook_dir", "Medallion")
    capacity_id = args.capacity_id if args.capacity_id is not None else params.get("capacity_id")
    workspace_description = (
        args.workspace_description
        if args.workspace_description is not None
        else params.get("workspace_description", "Managed by deploy_medallion_workspaces.py")
    )
    workspace_names = params.get("workspace_names", {})
    lakehouse_names = params.get("lakehouse_names", {})
    notebook_candidates = params.get("notebooks", DEFAULT_NOTEBOOKS)
    pipelines_by_layer = dict(DEFAULT_PIPELINES_BY_LAYER)
    pipelines_by_layer.update(params.get("pipelines_by_layer", {}))
    workspace_ids_output = (
        args.workspace_ids_output
        if args.workspace_ids_output is not None
        else params.get("workspace_ids_output", DEFAULT_WORKSPACE_IDS_OUTPUT)
    )

    try:
        environments = parse_csv_values(environments_raw, "environment")
        medallion_lakehouses = parse_csv_values(medallion_lakehouses_raw, "medallion lakehouse")
    except ValueError as error:
        print(f"❌ {error}")
        sys.exit(1)

    if args.workspace != "all":
        if args.workspace not in environments:
            print(
                f"⚠️ Workspace '{args.workspace}' was selected but is not present in environments: "
                f"{', '.join(environments)}"
            )
            print("   Proceeding with selected workspace only.")
        environments = [args.workspace]

    if not os.path.isdir(notebook_dir):
        print(f"❌ Notebook directory not found: {notebook_dir}")
        sys.exit(1)

    client = FabricClient(access_token)

    print("🚀 Starting medallion deployment...")
    print(f"   Workspaces: {', '.join(environments)}")
    print(f"   Lakehouses per workspace: {', '.join(medallion_lakehouses)}")
    print(f"   Notebook dir: {notebook_dir}")
    print(f"   Params file: {args.params_file}")
    print(f"   Workspace IDs output: {workspace_ids_output}")

    summary = {
        "workspaces_created_or_found": 0,
        "lakehouses_created_or_found": 0,
        "notebooks_deployed": 0,
        "notebooks_skipped": 0,
        "notebooks_failed": 0,
        "pipelines_deployed": 0,
        "pipelines_skipped": 0,
        "pipelines_failed": 0,
        "capacity_assignments_succeeded": 0,
        "capacity_assignments_failed": 0,
    }
    workspace_id_records = []

    for environment in environments:
        workspace_name = resolve_workspace_name(environment, prefix, workspace_names)

        print("\n" + "=" * 72)
        print(f"📦 Workspace: {environment}")
        print("=" * 72)

        print(f"🧭 Ensuring workspace '{workspace_name}'...")
        workspace = client.get_or_create_workspace(
            workspace_name,
            description=workspace_description,
            capacity_id=capacity_id,
        )
        workspace_id = workspace["id"]
        summary["workspaces_created_or_found"] += 1
        print(f"   ✅ Workspace ready: {workspace_name} ({workspace_id})")

        if capacity_id:
            print(f"🧲 Assigning workspace to capacity '{capacity_id}'...")
            try:
                assignment = client.assign_workspace_to_capacity(workspace_id, capacity_id)
                summary["capacity_assignments_succeeded"] += 1
                print(
                    "   ✅ Capacity assignment complete "
                    f"(HTTP {assignment['statusCode']}, {assignment['endpoint']})"
                )
            except Exception as error:  # pylint: disable=broad-except
                summary["capacity_assignments_failed"] += 1
                print(f"   ❌ Capacity assignment failed: {error}")

        # ── Deploy notebooks first so IDs are available for pipeline resolution ──
        notebook_id_map: Dict[str, str] = {}
        notebook_files = choose_existing_notebooks(notebook_dir, notebook_candidates)

        if not notebook_files:
            print("   ⚠️ No notebooks found for deployment, skipping notebook deployment")
        else:
            print("\n📓 Deploying notebooks...")
            for notebook_file in notebook_files:
                notebook_path = os.path.join(notebook_dir, notebook_file)
                display_name = notebook_display_name(notebook_file)

                if args.skip_existing_notebooks and client.notebook_exists(workspace_id, display_name):
                    print(f"   ⏭️ Notebook already exists, skipped: {display_name}")
                    summary["notebooks_skipped"] += 1
                    nb_id = client.get_notebook_id(workspace_id, display_name)
                    if nb_id:
                        notebook_id_map[display_name] = nb_id
                    continue

                print(f"   📝 Deploying notebook: {display_name}")
                try:
                    content = load_notebook_content(notebook_path)
                    response = client.create_notebook(workspace_id, display_name, content)
                    if response.get("status") == "exists":
                        summary["notebooks_skipped"] += 1
                        print("      ⏭️ Already exists, skipped")
                        nb_id = client.get_notebook_id(workspace_id, display_name)
                        if nb_id:
                            notebook_id_map[display_name] = nb_id
                    else:
                        summary["notebooks_deployed"] += 1
                        print("      ✅ Deployed")
                        if response.get("id"):
                            notebook_id_map[display_name] = response["id"]
                except Exception as error:  # pylint: disable=broad-except
                    summary["notebooks_failed"] += 1
                    print(f"      ❌ Failed: {error}")

        workspace_lakehouses = []
        workspace_pipelines = []
        for lakehouse_key in medallion_lakehouses:
            lakehouse_name = resolve_lakehouse_name(lakehouse_key, lakehouse_suffix, lakehouse_names)
            print(f"🏠 Ensuring lakehouse '{lakehouse_name}'...")
            lakehouse = client.get_or_create_lakehouse(workspace_id, lakehouse_name)
            summary["lakehouses_created_or_found"] += 1
            print(f"   ✅ Lakehouse ready: {lakehouse.get('displayName')} ({lakehouse.get('id')})")
            workspace_lakehouses.append(
                {
                    "name": lakehouse.get("displayName"),
                    "id": lakehouse.get("id"),
                    "medallionLayer": lakehouse_key,
                }
            )

            pipeline_candidates = pipelines_by_layer.get(lakehouse_key, [])
            pipeline_files = choose_existing_files(notebook_dir, pipeline_candidates)

            for pipeline_file in pipeline_files:
                pipeline_path = os.path.join(notebook_dir, pipeline_file)
                pipeline_content = load_json_content(pipeline_path)
                display_name = pipeline_display_name(pipeline_file, pipeline_content)
                pipeline_content = resolve_notebook_references(
                    pipeline_content, workspace_id, notebook_id_map, client
                )

                if args.skip_existing_pipelines and client.pipeline_exists(workspace_id, display_name):
                    print(f"   ⏭️ Pipeline already exists, skipped: {display_name}")
                    summary["pipelines_skipped"] += 1
                    continue

                print(f"🧩 Deploying pipeline: {display_name}")
                try:
                    response = client.create_pipeline(workspace_id, display_name, pipeline_content)
                    workspace_pipelines.append(
                        {
                            "name": display_name,
                            "id": response.get("id", display_name),
                            "medallionLayer": lakehouse_key,
                            "sourcePath": pipeline_file,
                        }
                    )
                    if response.get("status") == "exists":
                        summary["pipelines_skipped"] += 1
                        print("   ⏭️ Pipeline already exists, skipped")
                    else:
                        summary["pipelines_deployed"] += 1
                        print("   ✅ Pipeline deployed")
                except Exception as error:  # pylint: disable=broad-except
                    print(f"   ⚠️ Pipeline definition rejected, creating empty pipeline shell instead: {error}")
                    try:
                        shell_response = client.create_pipeline_shell(
                            workspace_id,
                            display_name,
                            description=(
                                "Created by deploy_medallion_workspaces.py. "
                                "Source pipeline JSON could not be applied automatically."
                            ),
                        )
                        workspace_pipelines.append(
                            {
                                "name": display_name,
                                "id": shell_response.get("id", display_name),
                                "medallionLayer": lakehouse_key,
                                "sourcePath": pipeline_file,
                            }
                        )
                        if shell_response.get("status") == "exists":
                            summary["pipelines_skipped"] += 1
                            print("   ⏭️ Pipeline already exists, skipped")
                        else:
                            summary["pipelines_deployed"] += 1
                            print("   ✅ Empty pipeline shell created")
                    except Exception as shell_error:  # pylint: disable=broad-except
                        summary["pipelines_failed"] += 1
                        print(f"   ❌ Pipeline deployment failed: {shell_error}")

        workspace_id_records.append(
            {
                "environment": environment,
                "workspaceName": workspace_name,
                "workspaceId": workspace_id,
                "lakehouses": workspace_lakehouses,
                "pipelines": workspace_pipelines,
            }
        )

    workspace_ids_payload = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "capacityId": capacity_id,
        "sourceParametersFile": args.params_file,
        "workspaces": workspace_id_records,
    }
    write_workspace_ids(workspace_ids_output, workspace_ids_payload)
    print(f"\n🧾 Workspace IDs saved to: {workspace_ids_output}")

    print("\n" + "=" * 72)
    print("📊 Summary")
    print("=" * 72)
    print(f"Workspaces ready: {summary['workspaces_created_or_found']}")
    print(f"Lakehouses ready: {summary['lakehouses_created_or_found']}")
    print(f"Pipelines deployed: {summary['pipelines_deployed']}")
    print(f"Pipelines skipped: {summary['pipelines_skipped']}")
    print(f"Pipelines failed: {summary['pipelines_failed']}")
    print(f"Notebooks deployed: {summary['notebooks_deployed']}")
    print(f"Notebooks skipped: {summary['notebooks_skipped']}")
    print(f"Notebooks failed: {summary['notebooks_failed']}")
    if capacity_id:
        print(f"Capacity assignments succeeded: {summary['capacity_assignments_succeeded']}")
        print(f"Capacity assignments failed: {summary['capacity_assignments_failed']}")

    if (
        summary["notebooks_failed"] > 0
        or summary["pipelines_failed"] > 0
        or summary["capacity_assignments_failed"] > 0
    ):
        sys.exit(1)


if __name__ == "__main__":
    main()
