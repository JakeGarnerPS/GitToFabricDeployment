import os
import json
from typing import Optional
import requests

FABRIC_API_BASE_URL = "https://api.fabric.microsoft.com/v1"


class LakehouseClient:
    def __init__(self, workspace_id: str, access_token: str):
        self.workspace_id = workspace_id
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def create_lakehouse(self, name: str) -> dict:
        url = f"{FABRIC_API_BASE_URL}/workspaces/{self.workspace_id}/lakehouses"
        payload = {"displayName": name}
        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_lakehouse(self, name: str) -> Optional[dict]:
        url = f"{FABRIC_API_BASE_URL}/workspaces/{self.workspace_id}/lakehouses"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        for lh in response.json().get("value", []):
            if lh.get("displayName") == name:
                return lh
        return None

    def upload_file_to_lakehouse(self, lakehouse_id: str, file_path: str, target_folder: str) -> dict:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        filename = os.path.basename(file_path)
        url = (
            f"{FABRIC_API_BASE_URL}/workspaces/{self.workspace_id}/lakehouses/{lakehouse_id}"
            f"/files/{target_folder}/{filename}"
        )
        with open(file_path, "rb") as f:
            files = {"file": (filename, f)}
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.post(url, files=files, headers=headers)
        response.raise_for_status()
        return response.json()
