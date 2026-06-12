import base64
import json
from typing import Dict, List, Optional

import requests

from .constants import FABRIC_API_BASE_URL
from .utils import build_platform_payload_b64, normalize_pipeline_definition


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

    def get_git_connection(self, workspace_id: str) -> Optional[dict]:
        url = f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/git/connection"
        response = requests.get(url, headers=self.headers)
        if response.status_code in (404, 400):
            return None
        response.raise_for_status()
        data = response.json()
        if not data.get("gitProviderDetails") and not data.get("gitSyncDetails"):
            return None
        return data

    def connect_git(self, workspace_id: str, git_provider_details: dict, git_credentials: dict) -> None:
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
