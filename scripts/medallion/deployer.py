import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from .utils import (
    choose_existing_notebooks,
    choose_existing_files,
    discover_tier_items,
    load_json_content,
    load_notebook_content,
    notebook_display_name,
    pipeline_display_name,
    resolve_notebook_references,
    retry_create_after_delete,
)


def ensure_workspace_and_capacity(client, workspace_name: str, workspace_description: str, capacity_id: str, summary: dict):
    workspace = client.get_or_create_workspace(workspace_name, description=workspace_description, capacity_id=capacity_id)
    workspace_id = workspace["id"]
    summary["workspaces_created_or_found"] += 1
    if capacity_id:
        try:
            assignment = client.assign_workspace_to_capacity(workspace_id, capacity_id)
            summary["capacity_assignments_succeeded"] += 1
        except Exception:
            summary["capacity_assignments_failed"] += 1
    return workspace


def try_git_sync(args, params, tier: str, environment: str, prod_environment: str, client, workspace_id: str, workspace_name: str, tier_key: str, workspace_id_records: list) -> bool:
    """Perform Git sync flow. Returns True if REST path should be skipped (i.e. handled by Git sync)."""
    if not args.git_sync or environment.lower() == prod_environment.lower():
        return False

    git_details = __import__("medallion.git", fromlist=["build_git_provider_details"]).build_git_provider_details(args, params, tier)
    missing = [k for k in ("repositoryName", "branchName", "ownerName")
               if not git_details.get(k) and k != "ownerName" or
               (k == "ownerName" and git_details.get("gitProviderType") == "GitHub" and not git_details.get(k))]
    if git_details.get("gitProviderType") == "AzureDevOps":
        missing = [k for k in ("repositoryName", "branchName", "organizationName", "projectName") if not git_details.get(k)]
    if missing:
        workspace_id_records.append({
            "tier": tier, "environment": environment,
            "workspaceName": workspace_name, "workspaceId": workspace_id,
            "lakehouses": [], "pipelines": [],
        })
        return True

    git_credentials = __import__("medallion.git", fromlist=["build_git_credentials"]).build_git_credentials(args, params)
    existing_connection = client.get_git_connection(workspace_id)
    if existing_connection:
        result = client.update_from_git(workspace_id)
    else:
        client.connect_git(workspace_id, git_details, git_credentials)
        result = client.initialize_git_connection(workspace_id, strategy="PreferRemote")

    if result.get("status") == "pending" and result.get("operationId"):
        op = client.poll_long_running_operation(result["operationId"])
        if op.get("status", "").lower() == "failed":
            pass

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
    return True


def deploy_rest_items(client, args, discovered: dict, tier: str, tier_key: str, tier_notebook_list: List[str], tier_pipeline_list: List[str], notebook_dir: str, workspace_id: str, summary: dict) -> Tuple[List[dict], List[dict]]:
    notebook_id_map: Dict[str, str] = {}

    # Build notebook list
    seen_nb_paths: set = set()
    all_notebook_items: List[dict] = []
    for item in discovered["notebooks"]:
        all_notebook_items.append(item)
        seen_nb_paths.add(item["path"])
    for rel_path in choose_existing_notebooks(notebook_dir, tier_notebook_list):
        if rel_path not in seen_nb_paths:
            all_notebook_items.append({"path": rel_path, "display_name": notebook_display_name(rel_path)})
            seen_nb_paths.add(rel_path)

    if all_notebook_items:
        for nb_item in all_notebook_items:
            notebook_path = os.path.join(notebook_dir, nb_item["path"])
            display_name = nb_item["display_name"]

            if args.skip_existing_notebooks and client.notebook_exists(workspace_id, display_name):
                summary["notebooks_skipped"] += 1
                nb_id = client.get_notebook_id(workspace_id, display_name)
                if nb_id:
                    notebook_id_map[display_name] = nb_id
                    if nb_item.get("logical_id"):
                        notebook_id_map[nb_item["logical_id"]] = nb_id
                continue

            try:
                content = load_notebook_content(notebook_path)
                existing_notebook_id = client.get_notebook_id(workspace_id, display_name)
                if existing_notebook_id:
                    response = client.update_notebook(workspace_id, existing_notebook_id, content)
                    summary["notebooks_deployed"] += 1
                    notebook_id_map[display_name] = existing_notebook_id
                    if nb_item.get("logical_id"):
                        notebook_id_map[nb_item["logical_id"]] = existing_notebook_id
                else:
                    response = retry_create_after_delete(lambda: client.create_notebook(workspace_id, display_name, content), display_name, "notebook")
                    if response.get("status") == "exists":
                        summary["notebooks_skipped"] += 1
                        nb_id = client.get_notebook_id(workspace_id, display_name)
                        if nb_id:
                            notebook_id_map[display_name] = nb_id
                            if nb_item.get("logical_id"):
                                notebook_id_map[nb_item["logical_id"]] = nb_id
                        continue
                    summary["notebooks_deployed"] += 1
                    if response.get("id"):
                        notebook_id_map[display_name] = response["id"]
                        if nb_item.get("logical_id"):
                            notebook_id_map[nb_item["logical_id"]] = response["id"]
            except Exception:
                summary["notebooks_failed"] += 1

    # Lakehouses
    workspace_lakehouses = []
    if discovered["lakehouses"]:
        lakehouses_to_deploy = [item["display_name"] for item in discovered["lakehouses"]]
    else:
        lakehouses_to_deploy = [f"{tier_key}_lakehouse"]

    for lh_name in lakehouses_to_deploy:
        lakehouse = client.get_or_create_lakehouse(workspace_id, lh_name)
        summary["lakehouses_created_or_found"] += 1
        workspace_lakehouses.append({"name": lakehouse.get("displayName"), "id": lakehouse.get("id"), "medallionLayer": tier_key})

    # Pipelines from JSON
    workspace_pipelines = []
    discovered_dp_names = {item["display_name"] for item in discovered["data_pipelines"]}
    pipeline_files = choose_existing_files(notebook_dir, tier_pipeline_list)

    for pipeline_file in pipeline_files:
        pipeline_path = os.path.join(notebook_dir, pipeline_file)
        pipeline_content = load_json_content(pipeline_path)
        display_name = pipeline_display_name(pipeline_file, pipeline_content)

        if display_name in discovered_dp_names:
            continue

        pipeline_content = resolve_notebook_references(pipeline_content, workspace_id, notebook_id_map, client)

        if args.skip_existing_pipelines and client.pipeline_exists(workspace_id, display_name):
            summary["pipelines_skipped"] += 1
            continue

        try:
            existing_pipeline_id = client.get_pipeline_id(workspace_id, display_name)
            if existing_pipeline_id:
                client.delete_pipeline(workspace_id, existing_pipeline_id)
            response = retry_create_after_delete(lambda: client.create_pipeline(workspace_id, display_name, pipeline_content), display_name, "pipeline")
            workspace_pipelines.append({"name": display_name, "id": response.get("id", display_name), "medallionLayer": tier_key, "sourcePath": pipeline_file})
            if response.get("status") == "exists":
                summary["pipelines_skipped"] += 1
            else:
                summary["pipelines_deployed"] += 1
        except Exception:
            try:
                shell_response = client.create_pipeline_shell(workspace_id, display_name)
                workspace_pipelines.append({"name": display_name, "id": shell_response.get("id", display_name), "medallionLayer": tier_key, "sourcePath": pipeline_file})
                if shell_response.get("status") == "exists":
                    summary["pipelines_skipped"] += 1
                else:
                    summary["pipelines_deployed"] += 1
            except Exception:
                summary["pipelines_failed"] += 1

    # Discovered DataPipeline folders
    for dp_item in discovered["data_pipelines"]:
        dp_folder = os.path.join(notebook_dir, dp_item["path"])
        dp_content_file = os.path.join(dp_folder, "pipeline-content.json")
        display_name = dp_item["display_name"]

        if not os.path.exists(dp_content_file):
            continue

        if args.skip_existing_pipelines and client.pipeline_exists(workspace_id, display_name):
            summary["pipelines_skipped"] += 1
            continue

        try:
            pipeline_content = load_json_content(dp_content_file)
            pipeline_content = resolve_notebook_references(pipeline_content, workspace_id, notebook_id_map, client)
            existing_pipeline_id = client.get_pipeline_id(workspace_id, display_name)
            if existing_pipeline_id:
                client.delete_pipeline(workspace_id, existing_pipeline_id)
            response = retry_create_after_delete(lambda: client.create_pipeline(workspace_id, display_name, pipeline_content), display_name, "DataPipeline")
            workspace_pipelines.append({"name": display_name, "id": response.get("id", display_name), "medallionLayer": tier_key, "sourcePath": dp_item["path"]})
            if response.get("status") == "exists":
                summary["pipelines_skipped"] += 1
            else:
                summary["pipelines_deployed"] += 1
        except Exception:
            try:
                shell_response = client.create_pipeline_shell(workspace_id, display_name)
                workspace_pipelines.append({"name": display_name, "id": shell_response.get("id", display_name), "medallionLayer": tier_key, "sourcePath": dp_item["path"]})
                if shell_response.get("status") == "exists":
                    summary["pipelines_skipped"] += 1
                else:
                    summary["pipelines_deployed"] += 1
            except Exception:
                summary["pipelines_failed"] += 1

    return workspace_lakehouses, workspace_pipelines
