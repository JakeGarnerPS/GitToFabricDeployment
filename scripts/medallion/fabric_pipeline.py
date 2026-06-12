import json
import time
from typing import Dict, List, Optional
import requests

FABRIC_API_BASE_URL = "https://api.fabric.microsoft.com/v1"


class FabricDeploymentClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def create_deployment_pipeline(self, pipeline_config: Dict) -> Dict:
        url = f"{FABRIC_API_BASE_URL}/deploymentPipelines"
        payload = {
            "displayName": pipeline_config["displayName"],
            "description": pipeline_config.get("description", ""),
            "stages": pipeline_config["stages"],
        }
        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def list_deployment_pipelines(self) -> List[Dict]:
        url = f"{FABRIC_API_BASE_URL}/deploymentPipelines"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json().get("value", [])

    def get_deployment_pipeline(self, pipeline_id: str) -> Dict:
        url = f"{FABRIC_API_BASE_URL}/deploymentPipelines/{pipeline_id}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def deploy_items(self, pipeline_id: str, source_stage_id: str, target_stage_id: str, items: Optional[List[str]] = None) -> Dict:
        url = f"{FABRIC_API_BASE_URL}/deploymentPipelines/{pipeline_id}/deploy"
        payload = {
            "sourceStageId": source_stage_id,
            "targetStageId": target_stage_id,
            "items": items or [],
            "options": {"allowOverwriteItems": True},
        }
        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_deployment_status(self, pipeline_id: str, deployment_id: str) -> Dict:
        url = f"{FABRIC_API_BASE_URL}/deploymentPipelines/{pipeline_id}/deployments/{deployment_id}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
