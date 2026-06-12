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
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import List

from medallion.client import FabricClient
from medallion.constants import (
    DEFAULT_ENVIRONMENTS,
    DEFAULT_PARAMS_FILE,
    DEFAULT_PROD_ENVIRONMENT,
    DEFAULT_TIER_LAKEHOUSES,
    DEFAULT_TIER_NOTEBOOKS,
    DEFAULT_TIER_PIPELINES,
    DEFAULT_TIERS,
    DEFAULT_WORKSPACE_IDS_OUTPUT,
)
from medallion.git import build_git_credentials, build_git_provider_details
from medallion.deployer import (
    ensure_workspace_and_capacity,
    try_git_sync,
    deploy_rest_items,
)
from medallion.utils import (
    choose_existing_notebooks,
    choose_existing_files,
    discover_tier_items,
    get_access_token_interactive,
    load_json_content,
    load_notebook_content,
    load_params_file,
    notebook_display_name,
    parse_csv_values,
    pipeline_display_name,
    resolve_notebook_references,
    resolve_tier_workspace_name,
    retry_create_after_delete,
    write_workspace_ids,
)


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
            workspace = ensure_workspace_and_capacity(client, workspace_name, workspace_description, capacity_id, summary)
            workspace_id = workspace["id"]
            print(f"   ✅ Workspace ready: {workspace_name} ({workspace_id})")

            if args.workspaces_only:
                continue

            # ── Git Integration sync path ─────────────────────────────────────────
            skipped_by_git = try_git_sync(args, params, tier, environment, prod_environment, client, workspace_id, workspace_name, tier_key, workspace_id_records)
            if skipped_by_git:
                continue

            if args.git_sync and environment.lower() == prod_environment.lower():
                print("   ℹ️ Skipping Git sync for Prod environment; deploying items through REST API instead.")

            workspace_lakehouses, workspace_pipelines = deploy_rest_items(client, args, discovered, tier, tier_key, tier_notebook_list, tier_pipeline_list, notebook_dir, workspace_id, summary)

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
