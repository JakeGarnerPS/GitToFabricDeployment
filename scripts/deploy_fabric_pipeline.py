#!/usr/bin/env python3
"""
Create and manage Fabric Deployment Pipelines using the Fabric REST API.

This script creates deployment pipelines for promoting workspaces across stages:
Dev → Staging → Prod

Usage:
    python deploy_fabric_pipeline.py --action create --config infra/fabric-deployment-pipeline.json
    python deploy_fabric_pipeline.py --action promote --from Dev --to Staging
    python deploy_fabric_pipeline.py --action status --workspace Road4_Bronze_Dev
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, Optional, List
import requests
from pathlib import Path


FABRIC_API_BASE_URL = "https://api.fabric.microsoft.com/v1"
POWER_BI_API_BASE_URL = "https://api.powerbi.com/v1.0/myorg"


class FabricDeploymentClient:
    """Client for managing Fabric Deployment Pipelines"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def create_deployment_pipeline(self, pipeline_config: Dict) -> Dict:
        """Create a deployment pipeline."""
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
        """List all deployment pipelines."""
        url = f"{FABRIC_API_BASE_URL}/deploymentPipelines"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json().get("value", [])

    def get_deployment_pipeline(self, pipeline_id: str) -> Dict:
        """Get a specific deployment pipeline."""
        url = f"{FABRIC_API_BASE_URL}/deploymentPipelines/{pipeline_id}"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def add_stage_to_pipeline(
        self,
        pipeline_id: str,
        stage_name: str,
        workspace_id: str,
        order: int = 0,
        description: str = "",
        is_public: bool = False,
    ) -> Dict:
        """Add a stage to a deployment pipeline."""
        url = f"{FABRIC_API_BASE_URL}/deploymentPipelines/{pipeline_id}/stages"

        payload = {
            "displayName": stage_name,
            "workspaceId": workspace_id,
            "order": order,
            "description": description,
            "isPublic": is_public,
        }

        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def deploy_items(
        self,
        pipeline_id: str,
        source_stage_id: str,
        target_stage_id: str,
        items: List[str],
    ) -> Dict:
        """Deploy items from source stage to target stage."""
        url = f"{FABRIC_API_BASE_URL}/deploymentPipelines/{pipeline_id}/deploy"

        payload = {
            "sourceStageId": source_stage_id,
            "targetStageId": target_stage_id,
            "items": items,
            "options": {
                "allowOverwriteItems": True,
            },
        }

        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_deployment_status(
        self,
        pipeline_id: str,
        deployment_id: str,
    ) -> Dict:
        """Get the status of a deployment."""
        url = f"{FABRIC_API_BASE_URL}/deploymentPipelines/{pipeline_id}/deployments/{deployment_id}"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def update_deployment_settings(
        self,
        pipeline_id: str,
        stage_id: str,
        settings: Dict,
    ) -> Dict:
        """Update deployment settings for a stage."""
        url = f"{FABRIC_API_BASE_URL}/deploymentPipelines/{pipeline_id}/stages/{stage_id}"

        response = requests.patch(url, json=settings, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def set_stage_users(
        self,
        pipeline_id: str,
        stage_id: str,
        users: List[str],
    ) -> Dict:
        """Set users who can edit items in a stage."""
        url = f"{FABRIC_API_BASE_URL}/deploymentPipelines/{pipeline_id}/stages/{stage_id}/users"

        payload = {
            "principalIds": users,
        }

        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_pipeline_items(
        self,
        pipeline_id: str,
        stage_id: str,
    ) -> List[Dict]:
        """Get items in a specific stage."""
        url = f"{FABRIC_API_BASE_URL}/deploymentPipelines/{pipeline_id}/stages/{stage_id}/items"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json().get("value", [])


def load_config(config_file: str) -> Dict:
    """Load deployment configuration from JSON file"""
    with open(config_file, 'r') as f:
        return json.load(f)


def create_deployment_pipeline(client: FabricDeploymentClient, config: Dict):
    """Create deployment pipeline from configuration."""
    print(f"Creating deployment pipeline: {config['displayName']}")
    
    try:
        pipeline = client.create_deployment_pipeline(config)
        print(f"✓ Pipeline created: {pipeline['id']}")
        return pipeline
    except requests.exceptions.RequestException as e:
        print(f"✗ Error creating pipeline: {e}")
        sys.exit(1)


def promote_stage(
    client: FabricDeploymentClient,
    pipeline_id: str,
    source_stage_id: str,
    target_stage_id: str,
    items: Optional[List[str]] = None
):
    """Promote items from one stage to another."""
    print(f"Promoting items from stage {source_stage_id} to {target_stage_id}")
    
    try:
        deployment = client.deploy_items(
            pipeline_id=pipeline_id,
            source_stage_id=source_stage_id,
            target_stage_id=target_stage_id,
            items=items or []
        )
        
        print(f"✓ Deployment started: {deployment['id']}")
        
        max_attempts = 30
        for attempt in range(max_attempts):
            status = client.get_deployment_status(
                pipeline_id=pipeline_id,
                deployment_id=deployment['id']
            )
            
            status_value = status.get('status', 'Unknown')
            print(f"  Deployment status: {status_value} ({attempt + 1}/{max_attempts})")
            
            if status_value in ['Completed', 'CompletedWithWarnings', 'Failed']:
                print(f"✓ Deployment {status_value}")
                if status_value == 'Failed':
                    errors = status.get('errors', [])
                    for error in errors:
                        print(f"  Error: {error}")
                    sys.exit(1)
                break
            
            if attempt < max_attempts - 1:
                time.sleep(10)
        
        return deployment
    except requests.exceptions.RequestException as e:
        print(f"✗ Error promoting stages: {e}")
        sys.exit(1)


def list_pipelines(client: FabricDeploymentClient):
    """List all deployment pipelines."""
    try:
        pipelines = client.list_deployment_pipelines()
        
        if not pipelines:
            print("No deployment pipelines found")
            return
        
        print(f"\n{'Pipeline Name':<40} {'ID':<40} {'Created':<20}")
        print("-" * 100)
        for pipeline in pipelines:
            name = pipeline.get('displayName', 'N/A')
            pid = pipeline.get('id', 'N/A')
            created = pipeline.get('createdDate', 'N/A')
            print(f"{name:<40} {pid:<40} {created:<20}")
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error listing pipelines: {e}")
        sys.exit(1)


def get_status(client: FabricDeploymentClient, pipeline_id: str):
    """Get deployment pipeline status."""
    try:
        pipeline = client.get_deployment_pipeline(pipeline_id)
        
        print(f"\nPipeline: {pipeline.get('displayName')}")
        print(f"ID: {pipeline.get('id')}")
        print(f"Description: {pipeline.get('description')}")
        print(f"Created: {pipeline.get('createdDate')}")
        
        stages = pipeline.get('stages', [])
        if stages:
            print(f"\nStages ({len(stages)}):")
            for stage in stages:
                print(f"  - {stage.get('displayName')} (ID: {stage.get('id')})")
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error getting status: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Manage Fabric Deployment Pipelines",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create deployment pipelines from config
  python deploy_fabric_pipeline.py --action create --config infra/fabric-deployment-pipelines.json
  
  # List pipelines
  python deploy_fabric_pipeline.py --action list
  
  # Get pipeline status
  python deploy_fabric_pipeline.py --action status --pipeline-id <pipeline-id>
  
  # Promote from Dev to Staging
  python deploy_fabric_pipeline.py --action promote --pipeline-id <pipeline-id> \\
    --from-stage <dev-stage-id> --to-stage <staging-stage-id>
        """
    )
    
    parser.add_argument(
        "--action",
        required=True,
        choices=["create", "promote", "list", "status"],
        help="Action to perform"
    )
    
    parser.add_argument(
        "--workspace-id",
        help="Workspace ID (not required for pipeline create/list/status operations)"
    )
    
    parser.add_argument(
        "--pipeline-id",
        help="Deployment pipeline ID"
    )
    
    parser.add_argument(
        "--config",
        help="Configuration file (for create action)"
    )
    
    parser.add_argument(
        "--from-stage",
        help="Source stage ID (for promote action)"
    )
    
    parser.add_argument(
        "--to-stage",
        help="Target stage ID (for promote action)"
    )
    
    parser.add_argument(
        "--items",
        nargs="+",
        help="Items to promote (optional)"
    )
    
    args = parser.parse_args()
    
    # Get access token from environment or Azure CLI
    access_token = None
    if "FABRIC_ACCESS_TOKEN" in os.environ:
        access_token = os.environ["FABRIC_ACCESS_TOKEN"]
    elif "AZURE_ACCESS_TOKEN" in os.environ:
        access_token = os.environ["AZURE_ACCESS_TOKEN"]
    else:
        try:
            import subprocess
            token_output = subprocess.run(
                ["az", "account", "get-access-token",
                 "--resource", "https://api.fabric.microsoft.com",
                 "--query", "accessToken", "-o", "tsv"],
                capture_output=True,
                text=True,
                check=True
            )
            access_token = token_output.stdout.strip()
        except Exception as e:
            print(f"Error getting access token: {e}")
            print("Make sure you're authenticated with: az login")
            sys.exit(1)

    client = FabricDeploymentClient(access_token)
    
    # Execute action
    if args.action == "create":
        if not args.config:
            parser.error("--config is required for create action")
        config = load_config(args.config)
        pipelines = config.get("pipelines")

        if not pipelines and isinstance(config, dict):
            props = config.get("properties", {})
            workspaces = props.get("workspaces", {})
            if workspaces:
                pipelines = []
                for tier_name, envs in workspaces.items():
                    stage_order = ["Dev", "Staging", "Prod"]
                    stages = []
                    for order, env_name in enumerate(stage_order):
                        env_details = envs.get(env_name)
                        if not env_details:
                            continue
                        stages.append({
                            "displayName": f"{tier_name} {env_name}",
                            "order": order,
                            "workspaceId": env_details["workspaceId"],
                            "description": env_details.get("workspaceName", ""),
                            "isPublic": env_name == "Prod",
                        })
                    if len(stages) >= 2:
                        pipelines.append({
                            "displayName": f"{tier_name} Deployment Pipeline",
                            "description": f"Deployment pipeline for the {tier_name} tier.",
                            "stages": stages,
                        })

        if not pipelines:
            parser.error("Unable to derive pipelines from config. Provide a config with a top-level 'pipelines' list.")

        for pipeline in pipelines:
            create_deployment_pipeline(client, pipeline)
    
    elif args.action == "list":
        list_pipelines(client)
    
    elif args.action == "status":
        if not args.pipeline_id:
            parser.error("--pipeline-id is required for status action")
        get_status(client, args.pipeline_id)
    
    elif args.action == "promote":
        if not all([args.pipeline_id, args.from_stage, args.to_stage]):
            parser.error("--pipeline-id, --from-stage, and --to-stage are required for promote action")
        promote_stage(
            client,
            args.pipeline_id,
            args.from_stage,
            args.to_stage,
            args.items
        )


if __name__ == "__main__":
    main()
