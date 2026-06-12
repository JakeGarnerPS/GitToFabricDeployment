import base64
import copy
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

import requests

from .constants import ITEM_NAME_RETRYABLE_ERROR, PLATFORM_SCHEMA_URL


def get_access_token_interactive() -> str:
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
        raise
    except subprocess.CalledProcessError:
        print("❌ Failed to get access token. Run 'az login' first.")
        raise


def choose_existing_notebooks(notebook_dir: str, candidates: List[str]) -> List[str]:
    return [filename for filename in candidates if os.path.exists(os.path.join(notebook_dir, filename))]


def load_notebook_content(path: str) -> str:
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
    client,
) -> dict:
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
                    type_props["notebookName"] = notebook_name

            existing_nb_id = type_props.get("notebookId")
            if existing_nb_id and existing_nb_id in notebook_id_map:
                type_props["notebookId"] = notebook_id_map[existing_nb_id]
                type_props["workspaceId"] = workspace_id

            if type_props.get("workspaceId") == "00000000-0000-0000-0000-000000000000":
                type_props["workspaceId"] = workspace_id
    return content


def notebook_display_name(notebook_filename: str) -> str:
    return Path(notebook_filename).stem


def pipeline_display_name(file_path: str, content: dict) -> str:
    return content.get("name", Path(file_path).stem)


def choose_existing_files(base_dir: str, candidates: List[str]) -> List[str]:
    return [relative_path for relative_path in candidates if os.path.exists(os.path.join(base_dir, relative_path))]


def discover_tier_items(tier_dir: str, base_dir: str) -> dict:
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
