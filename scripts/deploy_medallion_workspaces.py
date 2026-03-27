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
DEFAULT_TIERS = ["Bronze", "Silver", "Gold"]
DEFAULT_ENVIRONMENTS = ["Dev", "Prod", "Staging", "Feature"]
DEFAULT_PROD_ENVIRONMENT = "Prod"  # This environment gets no suffix in workspace names
DEFAULT_TIER_LAKEHOUSES = {
    "bronze": "bronze_lakehouse",
    "silver": "silver_lakehouse",
    "gold": "gold_lakehouse",
}
DEFAULT_TIER_NOTEBOOKS = {
    "bronze": [
        "Bronze/Notebooks/01_ingest_raw_sales_python.Notebook",
        "Bronze/Notebooks/01_ingest_raw_sales.Notebook",
    ],
    "silver": [
        "Silver/Notebooks/02_clean_sales_data.Notebook",
    ],
    "gold": [
        "Gold/Notebooks/03_curate_sales_mart.Notebook",
    ],
}
DEFAULT_TIER_PIPELINES = {
    "bronze": ["Bronze/Pipelines/bronze_ingest_pipeline.json"],
    "silver": ["Silver/Pipelines/silver_transform_pipeline.json"],
    "gold": ["Gold/Pipelines/gold_curated_pipeline.json"],
}
DEFAULT_PARAMS_FILE = "infra/medallion_workspace_params.json"
DEFAULT_WORKSPACE_IDS_OUTPUT = "infra/workspace_ids.json"
PLATFORM_SCHEMA_URL = (
    "https://developer.microsoft.com/json-schemas/"
    "fabric/gitIntegration/platformProperties/2.0.0/schema.json"
)
ITEM_NAME_RETRYABLE_ERROR = "ItemDisplayNameNotAvailableYet"


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

    def get_pipeline_id(self, workspace_id: str, display_name: str) -> Optional[str]:
        for pipeline in self.list_pipelines(workspace_id):
            if pipeline.get("displayName") == display_name:
                return pipeline.get("id")
        return None

    def pipeline_exists(self, workspace_id: str, display_name: str) -> bool:
        for pipeline in self.list_pipelines(workspace_id):
            if pipeline.get("displayName") == display_name:
                return True
        return False

    def delete_notebook(self, workspace_id: str, notebook_id: str) -> None:
        endpoints = [
            f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/notebooks/{notebook_id}",
            f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/items/{notebook_id}",
        ]

        last_status = None
        last_error = ""

        for url in endpoints:
            response = requests.delete(url, headers=self.headers)
            if response.status_code in (404, 405):
                last_status = response.status_code
                last_error = response.text
                continue
            if response.status_code not in (200, 202, 204):
                print(f"   API Response: {response.status_code}")
                print(f"   Error: {response.text}")
            response.raise_for_status()
            return

        raise RuntimeError(
            "Unable to delete notebook with available Fabric endpoints. "
            f"Last status: {last_status}, response: {last_error}"
        )

    def delete_pipeline(self, workspace_id: str, pipeline_id: str) -> None:
        endpoints = [
            f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/dataPipelines/{pipeline_id}",
            f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/items/{pipeline_id}",
        ]

        last_status = None
        last_error = ""

        for url in endpoints:
            response = requests.delete(url, headers=self.headers)
            if response.status_code in (404, 405):
                last_status = response.status_code
                last_error = response.text
                continue
            if response.status_code not in (200, 202, 204):
                print(f"   API Response: {response.status_code}")
                print(f"   Error: {response.text}")
            response.raise_for_status()
            return

        raise RuntimeError(
            "Unable to delete pipeline with available Fabric endpoints. "
            f"Last status: {last_status}, response: {last_error}"
        )

    def create_notebook(self, workspace_id: str, display_name: str, content: str) -> dict:
        url = f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/notebooks"

        notebook_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        payload = {
            "displayName": display_name,
            "definition": {
                "parts": [
                    {
                        "path": "notebook-content.py",
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

    def update_notebook(self, workspace_id: str, notebook_id: str, content: str) -> dict:
        """Update an existing notebook definition in-place."""
        notebook_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        payload = {
            "definition": {
                "parts": [
                    {
                        "path": "notebook-content.py",
                        "payloadType": "InlineBase64",
                        "payload": notebook_b64,
                    }
                ],
            },
        }

        endpoints = [
            f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/notebooks/{notebook_id}/updateDefinition",
            f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/items/{notebook_id}/updateDefinition",
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

    # ── Fabric Git Integration API ─────────────────────────────────────────────

    def get_git_connection(self, workspace_id: str) -> Optional[dict]:
        """Return the current Git connection for the workspace, or None if not connected."""
        url = f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/git/connection"
        response = requests.get(url, headers=self.headers)
        if response.status_code in (404, 400):
            return None
        response.raise_for_status()
        data = response.json()
        # A workspace with no Git connection returns an empty or specific payload
        if not data.get("gitProviderDetails") and not data.get("gitSyncDetails"):
            return None
        return data

    def connect_git(self, workspace_id: str, git_provider_details: dict, git_credentials: dict) -> None:
        """Connect a workspace to a Git repository."""
        url = f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/git/connect"
        payload = {
            "gitProviderDetails": git_provider_details,
            "myGitCredentials": git_credentials,
        }
        response = requests.post(url, json=payload, headers=self.headers)
        if response.status_code not in (200, 201, 202):
            print(f"   API Response: {response.status_code}")
            print(f"   Error: {response.text}")
        response.raise_for_status()

    def initialize_git_connection(self, workspace_id: str, strategy: str = "PreferRemote") -> dict:
        """Initialize the Git connection after first connect.

        ``strategy`` is one of:
          - ``PreferRemote``    — overwrite workspace items with what is in Git (safest for deploy)
          - ``PreferWorkspace`` — keep workspace items when there is a conflict
        """
        url = f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/git/initializeConnection"
        payload = {"initializationStrategy": strategy}
        response = requests.post(url, json=payload, headers=self.headers)
        if response.status_code not in (200, 201, 202):
            print(f"   API Response: {response.status_code}")
            print(f"   Error: {response.text}")
        response.raise_for_status()
        if response.status_code == 202:
            data = response.json() if response.text else {}
            operation_id = (
                response.headers.get("x-ms-operation-id")
                or data.get("operationId")
            )
            return {"status": "pending", "operationId": operation_id}
        return {"status": "complete"}

    def update_from_git(self, workspace_id: str) -> dict:
        """Pull latest changes from Git into the workspace (PreferRemote conflict resolution)."""
        url = f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/git/updateFromGit"
        payload = {
            "conflictResolution": {
                "conflictResolutionType": "Workspace",
                "conflictResolutionPolicy": "PreferRemote",
            },
            "options": {
                "allowOverrideItems": True,
            },
        }
        response = requests.post(url, json=payload, headers=self.headers)
        if response.status_code not in (200, 201, 202):
            print(f"   API Response: {response.status_code}")
            print(f"   Error: {response.text}")
        response.raise_for_status()
        if response.status_code == 202:
            data = response.json() if response.text else {}
            operation_id = (
                response.headers.get("x-ms-operation-id")
                or data.get("operationId")
            )
            return {"status": "pending", "operationId": operation_id}
        return {"status": "complete"}

    def poll_long_running_operation(self, operation_id: str, timeout: int = 300) -> dict:
        """Poll a Fabric long-running operation until it completes or times out."""
        url = f"{FABRIC_API_BASE_URL}/operations/{operation_id}"
        end_time = time.time() + timeout
        while time.time() < end_time:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            status = data.get("status", "").lower()
            if status in ("succeeded", "completed", "failed", "cancelled"):
                return data
            time.sleep(5)
        raise TimeoutError(
            f"Operation '{operation_id}' did not complete within {timeout}s."
        )


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


def load_notebook_content(path: str) -> str:
    """Read notebook content from a .Notebook folder (notebook-content.py) or a plain file."""
    if os.path.isdir(path):
        py_path = os.path.join(path, "notebook-content.py")
        with open(py_path, "r", encoding="utf-8") as handle:
            return handle.read()
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


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


def is_retryable_name_lock_error(error: Exception) -> bool:
    if not isinstance(error, requests.HTTPError):
        return False

    response = error.response
    if response is None or response.status_code != 400:
        return False

    return ITEM_NAME_RETRYABLE_ERROR in response.text


def retry_create_after_delete(create_operation, display_name: str, item_kind: str) -> dict:
    retry_delays = [5, 10, 20, 30]
    last_error = None

    for attempt_index, delay_seconds in enumerate([0] + retry_delays, start=1):
        if delay_seconds:
            print(
                f"   ⏳ Waiting {delay_seconds}s for deleted {item_kind} name '{display_name}' "
                "to become available"
            )
            time.sleep(delay_seconds)

        try:
            return create_operation()
        except Exception as error:  # pylint: disable=broad-except
            if not is_retryable_name_lock_error(error):
                raise
            last_error = error
            print(
                f"   ⚠️ Fabric has not released the deleted {item_kind} name '{display_name}' yet "
                f"(attempt {attempt_index}/{len(retry_delays) + 1})"
            )

    if last_error is not None:
        raise last_error

    raise RuntimeError(f"Failed to create {item_kind} '{display_name}' after retries.")


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
    """Replace notebookName placeholders and stale logicalId references in TridentNotebook
    activities with real Fabric item IDs for the target workspace.

    ``notebook_id_map`` may be keyed by display name OR by logicalId — both are checked.
    """
    content = copy.deepcopy(content)
    if "properties" in content:
        activities = content["properties"].get("activities", [])
    else:
        activities = content.get("activities", [])

    for activity in activities:
        if activity.get("type") == "TridentNotebook":
            type_props = activity.setdefault("typeProperties", {})

            # Resolve notebookName placeholder → real notebookId
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

            # Replace stale logicalId stored as notebookId (written by Git-sync into
            # pipeline-content.json) with the real Fabric item GUID for this workspace
            existing_nb_id = type_props.get("notebookId")
            if existing_nb_id and existing_nb_id in notebook_id_map:
                type_props["notebookId"] = notebook_id_map[existing_nb_id]
                type_props["workspaceId"] = workspace_id

            # Patch placeholder workspaceId written by Git-synced pipeline definitions
            if type_props.get("workspaceId") == "00000000-0000-0000-0000-000000000000":
                type_props["workspaceId"] = workspace_id
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


def discover_tier_items(tier_dir: str, base_dir: str) -> dict:
    """Scan a tier folder for Fabric item folders identified by their .platform files.

    Walks ``tier_dir`` recursively and returns all item folders that contain a
    ``.platform`` file with a recognised ``metadata.type`` (Notebook, Lakehouse,
    or DataPipeline).

    Args:
        tier_dir: Absolute or relative path to the tier folder (e.g. ``Bronze/``).
        base_dir: Root used to compute relative paths in the returned records.

    Returns:
        A dict with keys ``'notebooks'``, ``'lakehouses'``, ``'data_pipelines'``,
        each a list of ``{'path': <relative-to-base_dir>, 'display_name': str}``.
    """
    discovered: dict = {"notebooks": [], "lakehouses": [], "data_pipelines": []}

    if not os.path.isdir(tier_dir):
        return discovered

    for root, _dirs, files in os.walk(tier_dir):
        if ".platform" not in files:
            continue

        platform_path = os.path.join(root, ".platform")
        try:
            with open(platform_path, "r", encoding="utf-8") as fh:
                platform_data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue

        item_type = platform_data.get("metadata", {}).get("type", "")
        display_name = platform_data.get("metadata", {}).get("displayName") or Path(root).stem
        logical_id = platform_data.get("config", {}).get("logicalId")
        rel_path = os.path.relpath(root, base_dir)

        if item_type == "Notebook":
            discovered["notebooks"].append({"path": rel_path, "display_name": display_name, "logical_id": logical_id})
        elif item_type == "Lakehouse":
            discovered["lakehouses"].append({"path": rel_path, "display_name": display_name, "logical_id": logical_id})
        elif item_type == "DataPipeline":
            discovered["data_pipelines"].append({"path": rel_path, "display_name": display_name, "logical_id": logical_id})

    return discovered


def parse_csv_values(raw_values: str, label: str, lowercase: bool = True) -> List[str]:
    if lowercase:
        values = [value.strip().lower() for value in raw_values.split(",") if value.strip()]
    else:
        values = [value.strip() for value in raw_values.split(",") if value.strip()]
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


def resolve_tier_workspace_name(
    tier: str,
    environment: str,
    prefix: str,
    prod_environment: str,
    workspace_names: dict,
) -> str:
    """Return the workspace display name for a tier + environment combination.

    The prod environment gets no suffix: {prefix}_{tier}  (e.g., Road4_Bronze).
    All other environments get:         {prefix}_{tier}_{environment}  (e.g., Road4_Bronze_Dev).
    Explicit overrides keyed as '{tier}_{environment}' in workspace_names take precedence.
    """
    key = f"{tier}_{environment}"
    explicit = workspace_names.get(key)
    if explicit:
        return explicit
    if environment.lower() == prod_environment.lower():
        return f"{prefix}_{tier}"
    return f"{prefix}_{tier}_{environment}"


def write_workspace_ids(output_path: str, payload: dict) -> None:
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def build_git_provider_details(args, params: dict, tier: str) -> dict:
    """Build the gitProviderDetails payload for the Fabric Git connect API.

    The ``directoryName`` is always set to ``/{tier}`` so each workspace is
    scoped to its own tier folder in the repository.
    """
    git_params = params.get("git_connection", {})
    provider = args.git_provider or git_params.get("git_provider_type", "GitHub")
    owner = args.git_org or git_params.get("owner_name", "")
    repo = args.git_repo or git_params.get("repository_name", "")
    branch = args.git_branch or git_params.get("branch_name", "")

    if not branch:
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=True,
            )
            branch = result.stdout.strip()
        except Exception:  # pylint: disable=broad-except
            pass

    details: dict = {
        "gitProviderType": provider,
        "repositoryName": repo,
        "branchName": branch,
        "directoryName": f"/{tier}",
    }

    if provider == "AzureDevOps":
        details["organizationName"] = owner
        details["projectName"] = args.git_project or git_params.get("project_name", "")
    else:
        details["ownerName"] = owner

    return details


def build_git_credentials(args, params: dict) -> dict:
    """Build the myGitCredentials payload for the Fabric Git connect API.

    Fabric expects a ``source`` field in ``myGitCredentials``.

    Supported sources:
    - ``Automatic``            — uses the caller's Entra ID / Azure AD token
    - ``ConfiguredConnection`` — uses an existing Fabric Git connection by ID

    Notes:
    - Some tenants do not allow ``Automatic`` for GitHub.
    - In that case, use ``ConfiguredConnection`` with ``--git-connection-id``
      (or ``git_connection_id`` in the params file).
    """
    git_params = params.get("git_connection", {})
    cred_type = (
        getattr(args, "git_credential_type", None)
        or git_params.get("git_credential_type", "Automatic")
    )

    if cred_type == "ConfiguredConnection":
        connection_id = (
            getattr(args, "git_connection_id", None)
            or git_params.get("git_connection_id", "")
        )
        if not connection_id:
            raise ValueError(
                "--git-connection-id (or git_connection_id in git_connection params) "
                "is required when git_credential_type is ConfiguredConnection."
            )
        return {"source": "ConfiguredConnection", "connectionId": connection_id}

    if cred_type == "PersonalAccessToken":
        raise ValueError(
            "git_credential_type=PersonalAccessToken is not supported by the Fabric "
            "git/connect API in this script. Use ConfiguredConnection with a Fabric "
            "connection ID instead."
        )

    return {"source": "Automatic"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy medallion Bronze/Silver/Gold tier workspaces to Microsoft Fabric",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/deploy_medallion_workspaces.py --interactive\n"
            "  python scripts/deploy_medallion_workspaces.py --interactive --workspace Dev\n"
            "  python scripts/deploy_medallion_workspaces.py --interactive --workspace Prod\n"
            "  python scripts/deploy_medallion_workspaces.py --interactive --workspace Staging\n"
            "  python scripts/deploy_medallion_workspaces.py --interactive --workspace all\n"
            "  python scripts/deploy_medallion_workspaces.py --interactive --workspaces-only\n"
            "  python scripts/deploy_medallion_workspaces.py --token <token> --params-file infra/medallion_workspace_params.json\n"
            "  python scripts/deploy_medallion_workspaces.py --tiers Bronze,Silver --environments Dev,Prod --capacity-id <id>"
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
        help="Workspace naming prefix (default: Road4)",
    )
    parser.add_argument(
        "--tiers",
        default=None,
        help="Comma-separated medallion tiers to deploy (default: Bronze,Silver,Gold)",
    )
    parser.add_argument(
        "--environments",
        default=None,
        help="Comma-separated environments to deploy per tier (default: Dev,Prod,Staging,Feature)",
    )
    parser.add_argument(
        "--prod-environment",
        default=None,
        help=(
            "Environment name that gets no suffix in workspace names (default: Prod). "
            "e.g., 'Road4_Bronze' instead of 'Road4_Bronze_Prod'"
        ),
    )
    parser.add_argument(
        "--workspace",
        default="all",
        help=(
            "Filter deployment to a single environment (e.g., Dev, Prod) across all tiers, "
            "or 'all' to deploy every environment (default: all)."
        ),
    )
    parser.add_argument(
        "--notebook-dir",
        default=None,
        help="Base directory containing tier notebook folders (default: current directory)",
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
    parser.add_argument(
        "--workspaces-only",
        action="store_true",
        help="Only create/verify workspaces and assign capacity. Skip lakehouses, notebooks, and pipelines.",
    )
    parser.add_argument(
        "--git-sync",
        action="store_true",
        help=(
            "Connect each workspace to its tier directory in the Git repo and sync items "
            "using the Fabric Git Integration API. Items are created with the correct "
            "logicalId values from .platform files, making subsequent Git syncs conflict-free. "
            "Skips individual REST API item creation."
        ),
    )
    parser.add_argument(
        "--git-provider",
        default=None,
        choices=["GitHub", "AzureDevOps"],
        help="Git provider type for --git-sync (default: GitHub)",
    )
    parser.add_argument(
        "--git-org",
        default=None,
        help="GitHub owner name or Azure DevOps organisation name for --git-sync",
    )
    parser.add_argument(
        "--git-repo",
        default=None,
        help="Repository name for --git-sync",
    )
    parser.add_argument(
        "--git-branch",
        default=None,
        help="Branch name for --git-sync (default: current git branch)",
    )
    parser.add_argument(
        "--git-project",
        default=None,
        help="Azure DevOps project name (only required when --git-provider AzureDevOps)",
    )
    parser.add_argument(
        "--git-credential-type",
        default=None,
        choices=["Automatic", "ConfiguredConnection", "PersonalAccessToken"],
        help=(
            "Credential type for the Fabric Git connect API (default: Automatic). "
            "Use ConfiguredConnection when your Fabric tenant does not allow the "
            "Automatic flow for GitHub connections."
        ),
    )
    parser.add_argument(
        "--git-connection-id",
        default=None,
        help="Fabric Git connection ID (required when --git-credential-type ConfiguredConnection)",
    )
    parser.add_argument(
        "--git-pat",
        default=None,
        help="Deprecated. Use --git-credential-type ConfiguredConnection and --git-connection-id instead.",
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

    prefix = args.prefix if args.prefix is not None else params.get("prefix", "Road4")
    tiers_raw = (
        args.tiers
        if args.tiers is not None
        else params.get("tiers", ",".join(DEFAULT_TIERS))
    )
    environments_raw = (
        args.environments
        if args.environments is not None
        else params.get("environments", ",".join(DEFAULT_ENVIRONMENTS))
    )
    prod_environment = (
        args.prod_environment
        if args.prod_environment is not None
        else params.get("prod_environment", DEFAULT_PROD_ENVIRONMENT)
    )
    notebook_dir = args.notebook_dir if args.notebook_dir is not None else params.get("notebook_dir", ".")
    capacity_id = args.capacity_id if args.capacity_id is not None else params.get("capacity_id")
    workspace_description = (
        args.workspace_description
        if args.workspace_description is not None
        else params.get("workspace_description", "Managed by deploy_medallion_workspaces.py")
    )
    workspace_names = params.get("workspace_names", {})
    tier_lakehouses = dict(DEFAULT_TIER_LAKEHOUSES)
    tier_lakehouses.update({k.lower(): v for k, v in params.get("tier_lakehouses", {}).items()})
    tier_notebooks = dict(DEFAULT_TIER_NOTEBOOKS)
    tier_notebooks.update({k.lower(): v for k, v in params.get("tier_notebooks", {}).items()})
    tier_pipelines = dict(DEFAULT_TIER_PIPELINES)
    tier_pipelines.update({k.lower(): v for k, v in params.get("tier_pipelines", {}).items()})
    workspace_ids_output = (
        args.workspace_ids_output
        if args.workspace_ids_output is not None
        else params.get("workspace_ids_output", DEFAULT_WORKSPACE_IDS_OUTPUT)
    )

    try:
        tiers = parse_csv_values(tiers_raw, "tier", lowercase=False)
        environments = parse_csv_values(environments_raw, "environment", lowercase=False)
    except ValueError as error:
        print(f"❌ {error}")
        sys.exit(1)

    if args.workspace != "all":
        matched = [e for e in environments if e.lower() == args.workspace.lower()]
        if not matched:
            print(
                f"⚠️ Environment '{args.workspace}' not found in: {', '.join(environments)}"
            )
            print("   Proceeding with selected environment only.")
        environments = matched if matched else [args.workspace]

    if not args.workspaces_only and not os.path.isdir(notebook_dir):
        print(f"❌ Notebook directory not found: {notebook_dir}")
        sys.exit(1)

    client = FabricClient(access_token)

    prod_label = f"('{prod_environment}' environment \u2192 no env suffix, e.g., {prefix}_Bronze)"
    print("🚀 Starting medallion deployment...")
    print(f"   Tiers: {', '.join(tiers)}")
    print(f"   Environments: {', '.join(environments)}")
    print(f"   Prod environment: {prod_label}")
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

    for tier in tiers:
        tier_key = tier.lower()
        tier_notebook_list = tier_notebooks.get(tier_key, [])
        tier_pipeline_list = tier_pipelines.get(tier_key, [])
        tier_lakehouse_name = tier_lakehouses.get(tier_key, f"{tier_key}_lakehouse")

        # Auto-discover all Fabric items (Notebooks, Lakehouses, DataPipelines) in the tier folder
        tier_folder = os.path.join(notebook_dir, tier)
        discovered = discover_tier_items(tier_folder, notebook_dir)
        if discovered["notebooks"] or discovered["lakehouses"] or discovered["data_pipelines"]:
            print(
                f"\n🔍 Discovered in {tier}/: "
                f"{len(discovered['notebooks'])} notebook(s), "
                f"{len(discovered['lakehouses'])} lakehouse(s), "
                f"{len(discovered['data_pipelines'])} DataPipeline(s)"
            )

        for environment in environments:
            workspace_name = resolve_tier_workspace_name(
                tier, environment, prefix, prod_environment, workspace_names
            )

            print("\n" + "=" * 72)
            print(f"📦 {tier} / {environment}  →  {workspace_name}")
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

            if args.workspaces_only:
                continue

            # ── Git Integration sync path ─────────────────────────────────────────
            if args.git_sync:
                git_details = build_git_provider_details(args, params, tier)
                missing = [k for k in ("repositoryName", "branchName", "ownerName")
                           if not git_details.get(k) and k != "ownerName" or
                           (k == "ownerName" and git_details.get("gitProviderType") == "GitHub" and not git_details.get(k))]
                if git_details.get("gitProviderType") == "AzureDevOps":
                    missing = [k for k in ("repositoryName", "branchName", "organizationName", "projectName")
                               if not git_details.get(k)]
                if missing:
                    print(f"   ❌ Git sync skipped — missing: {', '.join(missing)}. "
                          f"Set via --git-org / --git-repo / --git-branch or git_connection in params file.")
                    workspace_id_records.append({
                        "tier": tier, "environment": environment,
                        "workspaceName": workspace_name, "workspaceId": workspace_id,
                        "lakehouses": [], "pipelines": [],
                    })
                    continue

                print(f"\n🔗 Git sync: {git_details['gitProviderType']} "
                      f"{git_details.get('ownerName') or git_details.get('organizationName')}/"
                      f"{git_details['repositoryName']} "
                      f"@ {git_details['branchName']}{git_details['directoryName']}")
                try:
                    git_credentials = build_git_credentials(args, params)
                    existing_connection = client.get_git_connection(workspace_id)
                    if existing_connection:
                        print("   🔄 Already connected — updating from Git...")
                        result = client.update_from_git(workspace_id)
                    else:
                        cred_label = git_credentials["source"]
                        print(f"   🔌 Connecting workspace to Git repo (credentials: {cred_label})...")
                        client.connect_git(workspace_id, git_details, git_credentials)
                        print("   🚀 Initialising connection (PreferRemote — Git wins on conflict)...")
                        result = client.initialize_git_connection(workspace_id, strategy="PreferRemote")

                    if result.get("status") == "pending" and result.get("operationId"):
                        print("   ⏳ Waiting for Git sync to complete...")
                        op = client.poll_long_running_operation(result["operationId"])
                        if op.get("status", "").lower() == "failed":
                            err_msg = op.get("error", {}).get("message", "unknown error")
                            print(f"   ❌ Git sync failed: {err_msg}")
                        else:
                            print("   ✅ Git sync complete")
                    else:
                        print("   ✅ Git sync complete")

                except Exception as error:  # pylint: disable=broad-except
                    print(f"   ❌ Git sync error: {error}")
                    error_text = str(error)
                    if "GitCredentialsConfigurationNotSupported" in error_text:
                        print(
                            "   💡 This tenant does not support myGitCredentials.source=Automatic for this provider."
                        )
                        print(
                            "      Use --git-credential-type ConfiguredConnection and "
                            "--git-connection-id <fabric-connection-id>."
                        )

                # Collect item IDs from the synced workspace for workspace_ids.json
                workspace_lakehouses = [
                    {"name": lh.get("displayName"), "id": lh.get("id"), "medallionLayer": tier_key}
                    for lh in client.list_lakehouses(workspace_id)
                ]
                workspace_pipelines = [
                    {"name": pl.get("displayName"), "id": pl.get("id"), "medallionLayer": tier_key}
                    for pl in client.list_pipelines(workspace_id)
                ]
                workspace_id_records.append({
                    "tier": tier,
                    "environment": environment,
                    "workspaceName": workspace_name,
                    "workspaceId": workspace_id,
                    "lakehouses": workspace_lakehouses,
                    "pipelines": workspace_pipelines,
                })
                continue  # skip REST API item deployment

            # ── REST API item deployment path ────────────────────────────────────

            # ── Deploy this tier's notebooks first so IDs are available for pipeline resolution ──
            notebook_id_map: Dict[str, str] = {}

            # Build notebook list: discovered .Notebook folders first, then explicit params (no duplicates)
            seen_nb_paths: set = set()
            all_notebook_items: List[dict] = []
            for item in discovered["notebooks"]:
                all_notebook_items.append(item)
                seen_nb_paths.add(item["path"])
            for rel_path in choose_existing_notebooks(notebook_dir, tier_notebook_list):
                if rel_path not in seen_nb_paths:
                    all_notebook_items.append(
                        {"path": rel_path, "display_name": notebook_display_name(rel_path)}
                    )
                    seen_nb_paths.add(rel_path)

            if not all_notebook_items:
                print(f"   ⚠️ No notebooks found for {tier}, skipping notebook deployment")
            else:
                print(f"\n📓 Deploying {tier} notebooks ({len(all_notebook_items)} found)...")
                for nb_item in all_notebook_items:
                    notebook_path = os.path.join(notebook_dir, nb_item["path"])
                    display_name = nb_item["display_name"]

                    if args.skip_existing_notebooks and client.notebook_exists(workspace_id, display_name):
                        print(f"   ⏭️ Notebook already exists, skipped: {display_name}")
                        summary["notebooks_skipped"] += 1
                        nb_id = client.get_notebook_id(workspace_id, display_name)
                        if nb_id:
                            notebook_id_map[display_name] = nb_id
                            if nb_item.get("logical_id"):
                                notebook_id_map[nb_item["logical_id"]] = nb_id
                        continue

                    print(f"   📝 Deploying notebook: {display_name}")
                    try:
                        content = load_notebook_content(notebook_path)
                        existing_notebook_id = client.get_notebook_id(workspace_id, display_name)
                        if existing_notebook_id:
                            print("      ♻️ Existing notebook found, updating definition")
                            response = client.update_notebook(workspace_id, existing_notebook_id, content)
                            summary["notebooks_deployed"] += 1
                            notebook_id_map[display_name] = existing_notebook_id
                            if nb_item.get("logical_id"):
                                notebook_id_map[nb_item["logical_id"]] = existing_notebook_id
                            if response.get("status") == "pending":
                                print("      ✅ Update requested (async)")
                            else:
                                print("      ✅ Updated")
                        else:
                            response = retry_create_after_delete(
                                lambda: client.create_notebook(workspace_id, display_name, content),
                                display_name,
                                "notebook",
                            )
                            if response.get("status") == "exists":
                                summary["notebooks_skipped"] += 1
                                print("      ⏭️ Already exists, skipped")
                                nb_id = client.get_notebook_id(workspace_id, display_name)
                                if nb_id:
                                    notebook_id_map[display_name] = nb_id
                                    if nb_item.get("logical_id"):
                                        notebook_id_map[nb_item["logical_id"]] = nb_id
                                continue
                            summary["notebooks_deployed"] += 1
                            print("      ✅ Deployed")
                            if response.get("id"):
                                notebook_id_map[display_name] = response["id"]
                                if nb_item.get("logical_id"):
                                    notebook_id_map[nb_item["logical_id"]] = response["id"]
                    except Exception as error:  # pylint: disable=broad-except
                        summary["notebooks_failed"] += 1
                        print(f"      ❌ Failed: {error}")

            # ── Deploy this tier's lakehouses ──
            workspace_lakehouses = []
            workspace_pipelines = []

            # Prefer lakehouses discovered from the tier folder; fall back to params default
            lakehouses_to_deploy = (
                [item["display_name"] for item in discovered["lakehouses"]]
                if discovered["lakehouses"]
                else [tier_lakehouse_name]
            )

            for lh_name in lakehouses_to_deploy:
                print(f"🏠 Ensuring lakehouse '{lh_name}'...")
                lakehouse = client.get_or_create_lakehouse(workspace_id, lh_name)
                summary["lakehouses_created_or_found"] += 1
                print(f"   ✅ Lakehouse ready: {lakehouse.get('displayName')} ({lakehouse.get('id')})")
                workspace_lakehouses.append(
                    {
                        "name": lakehouse.get("displayName"),
                        "id": lakehouse.get("id"),
                        "medallionLayer": tier_key,
                    }
                )

            # ── Deploy this tier's pipelines (JSON fallback — skipped if a .DataPipeline folder covers the same name) ──
            # Names already covered by discovered .DataPipeline folders take precedence.
            discovered_dp_names = {item["display_name"] for item in discovered["data_pipelines"]}
            pipeline_files = choose_existing_files(notebook_dir, tier_pipeline_list)

            for pipeline_file in pipeline_files:
                pipeline_path = os.path.join(notebook_dir, pipeline_file)
                pipeline_content = load_json_content(pipeline_path)
                display_name = pipeline_display_name(pipeline_file, pipeline_content)

                if display_name in discovered_dp_names:
                    print(f"   ⏭️ JSON pipeline '{display_name}' superseded by discovered .DataPipeline folder, skipping")
                    continue

                pipeline_content = resolve_notebook_references(
                    pipeline_content, workspace_id, notebook_id_map, client
                )

                if args.skip_existing_pipelines and client.pipeline_exists(workspace_id, display_name):
                    print(f"   ⏭️ Pipeline already exists, skipped: {display_name}")
                    summary["pipelines_skipped"] += 1
                    continue

                print(f"🧩 Deploying pipeline: {display_name}")
                try:
                    existing_pipeline_id = client.get_pipeline_id(workspace_id, display_name)
                    if existing_pipeline_id:
                        print("   ♻️ Existing pipeline found, replacing")
                        client.delete_pipeline(workspace_id, existing_pipeline_id)
                    response = retry_create_after_delete(
                        lambda: client.create_pipeline(workspace_id, display_name, pipeline_content),
                        display_name,
                        "pipeline",
                    )
                    workspace_pipelines.append(
                        {
                            "name": display_name,
                            "id": response.get("id", display_name),
                            "medallionLayer": tier_key,
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
                                "medallionLayer": tier_key,
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

            # ── Deploy discovered .DataPipeline folders ──
            if discovered["data_pipelines"]:
                print(f"\n🔗 Deploying {tier} DataPipeline folders ({len(discovered['data_pipelines'])} found)...")
            for dp_item in discovered["data_pipelines"]:
                dp_folder = os.path.join(notebook_dir, dp_item["path"])
                dp_content_file = os.path.join(dp_folder, "pipeline-content.json")
                display_name = dp_item["display_name"]

                if not os.path.exists(dp_content_file):
                    print(f"   ⚠️ Missing pipeline-content.json in {dp_item['path']}, skipping")
                    continue

                if args.skip_existing_pipelines and client.pipeline_exists(workspace_id, display_name):
                    print(f"   ⏭️ DataPipeline already exists, skipped: {display_name}")
                    summary["pipelines_skipped"] += 1
                    continue

                print(f"   🧩 Deploying DataPipeline: {display_name}")
                try:
                    pipeline_content = load_json_content(dp_content_file)
                    pipeline_content = resolve_notebook_references(
                        pipeline_content, workspace_id, notebook_id_map, client
                    )
                    existing_pipeline_id = client.get_pipeline_id(workspace_id, display_name)
                    if existing_pipeline_id:
                        print("      ♻️ Existing DataPipeline found, replacing")
                        client.delete_pipeline(workspace_id, existing_pipeline_id)
                    response = retry_create_after_delete(
                        lambda: client.create_pipeline(workspace_id, display_name, pipeline_content),
                        display_name,
                        "DataPipeline",
                    )
                    workspace_pipelines.append(
                        {
                            "name": display_name,
                            "id": response.get("id", display_name),
                            "medallionLayer": tier_key,
                            "sourcePath": dp_item["path"],
                        }
                    )
                    if response.get("status") == "exists":
                        summary["pipelines_skipped"] += 1
                        print("      ⏭️ DataPipeline already exists, skipped")
                    else:
                        summary["pipelines_deployed"] += 1
                        print("      ✅ DataPipeline deployed")
                except Exception as error:  # pylint: disable=broad-except
                    print(f"      ⚠️ DataPipeline definition rejected, creating empty shell instead: {error}")
                    try:
                        shell_response = client.create_pipeline_shell(
                            workspace_id,
                            display_name,
                            description=(
                                "Created by deploy_medallion_workspaces.py. "
                                "Source DataPipeline could not be applied automatically."
                            ),
                        )
                        workspace_pipelines.append(
                            {
                                "name": display_name,
                                "id": shell_response.get("id", display_name),
                                "medallionLayer": tier_key,
                                "sourcePath": dp_item["path"],
                            }
                        )
                        if shell_response.get("status") == "exists":
                            summary["pipelines_skipped"] += 1
                            print("      ⏭️ DataPipeline already exists, skipped")
                        else:
                            summary["pipelines_deployed"] += 1
                            print("      ✅ Empty DataPipeline shell created")
                    except Exception as shell_error:  # pylint: disable=broad-except
                        summary["pipelines_failed"] += 1
                        print(f"      ❌ DataPipeline deployment failed: {shell_error}")

            workspace_id_records.append(
                {
                    "tier": tier,
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
