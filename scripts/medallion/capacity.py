import json
import os
from datetime import datetime, timezone
from typing import Dict, List
import requests

FABRIC_API_BASE_URL = "https://api.fabric.microsoft.com/v1"


class CapacityClient:
    def __init__(self, access_token: str):
        self.headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    def assign_workspace_to_capacity(self, workspace_id: str, capacity_id: str):
        payload = {"capacityId": capacity_id}
        endpoints = [
            f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/assignToCapacity",
            f"{FABRIC_API_BASE_URL}/workspaces/{workspace_id}/capacityAssignments",
        ]
        last_status = 0
        last_text = ""
        last_endpoint = endpoints[0]
        for endpoint in endpoints:
            response = requests.post(endpoint, json=payload, headers=self.headers)
            if response.status_code in (200, 201, 202, 204):
                return response.status_code, endpoint, response.text
            if response.status_code in (404, 405):
                last_status = response.status_code
                last_text = response.text
                last_endpoint = endpoint
                continue
            return response.status_code, endpoint, response.text
        return last_status, last_endpoint, last_text

def load_workspace_ids(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Workspace IDs file not found: {path}")
    with open(path, 'r', encoding='utf-8') as handle:
        data = json.load(handle)
    workspaces = data.get('workspaces', [])
    normalized = []
    for row in workspaces:
        workspace_id = row.get('workspaceId')
        if not workspace_id:
            continue
        normalized.append({
            'environment': row.get('environment', row.get('layer', 'unknown')),
            'workspaceName': row.get('workspaceName', 'unknown'),
            'workspaceId': workspace_id,
        })
    if not normalized:
        raise ValueError('No workspace IDs found under the "workspaces" array.')
    return normalized

def write_results(path: str, payload: dict) -> None:
    output_dir = os.path.dirname(path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2)
