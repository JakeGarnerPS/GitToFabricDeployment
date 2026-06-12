import os
import base64
from pathlib import Path
from typing import Optional, List
import requests

FABRIC_API_BASE_URL = "https://api.fabric.microsoft.com/v1"


class NotebooksClient:
    def __init__(self, workspace_id: str, access_token: str):
        self.workspace_id = workspace_id
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    def create_notebook(self, name: str, content: str) -> dict:
        url = f"{FABRIC_API_BASE_URL}/workspaces/{self.workspace_id}/notebooks"
        notebook_b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        payload = {"displayName": name, "definition": {"parts": [{"path": "notebook-content.py","payloadType": "InlineBase64","payload": notebook_b64}]}}
        response = requests.post(url, json=payload, headers=self.headers)
        if response.status_code not in (200, 201, 202):
            print(f"   API Response: {response.status_code}")
            print(f"   Error: {response.text}")
        response.raise_for_status()
        if response.status_code == 202:
            return {"id": name, "displayName": name, "status": "pending"}
        return response.json()

    def update_notebook(self, notebook_id: str, content: str) -> dict:
        notebook_b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        payload = {"definition": {"parts": [{"path": "notebook-content.py","payloadType": "InlineBase64","payload": notebook_b64}]}}
        endpoints = [f"{FABRIC_API_BASE_URL}/workspaces/{self.workspace_id}/notebooks/{notebook_id}/updateDefinition", f"{FABRIC_API_BASE_URL}/workspaces/{self.workspace_id}/items/{notebook_id}/updateDefinition"]
        last_error = None
        for url in endpoints:
            response = requests.post(url, json=payload, headers=self.headers)
            if response.status_code in (404, 405):
                last_error = response.text
                continue
            response.raise_for_status()
            if response.status_code == 202:
                return {"id": notebook_id, "status": "pending"}
            return response.json() if response.text else {"id": notebook_id, "status": "updated"}
        raise RuntimeError(f"Unable to update notebook definition. Last error: {last_error}")

    def get_notebooks(self) -> List[dict]:
        url = f"{FABRIC_API_BASE_URL}/workspaces/{self.workspace_id}/notebooks"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json().get("value", [])

    def get_notebook_by_name(self, name: str) -> Optional[dict]:
        for nb in self.get_notebooks():
            if nb.get("displayName") == name:
                return nb
        return None

def load_notebook_content(file_path: str) -> str:
    if os.path.isdir(file_path):
        py_path = os.path.join(file_path, "notebook-content.py")
        with open(py_path, 'r') as f:
            return f.read()
    with open(file_path, 'r') as f:
        return f.read()

def get_notebook_display_name(file_path: str) -> str:
    return Path(file_path).stem
