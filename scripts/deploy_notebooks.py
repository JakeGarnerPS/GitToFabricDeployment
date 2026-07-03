#!/usr/bin/env python3
"""
Deploy Notebooks to Microsoft Fabric
This script uploads notebook files directly to a Fabric workspace using medallion.notebooks helpers.
"""

import os
import sys
from typing import List

from medallion.notebooks import NotebooksClient, load_notebook_content, get_notebook_display_name

NOTEBOOKS_DIR_DEFAULT = "Notebooks"


def discover_notebook_files(dir_path: str) -> List[str]:
    entries = []
    for name in os.listdir(dir_path):
        full = os.path.join(dir_path, name)
        if name.endswith('.Notebook') or name.endswith('.py') or os.path.isdir(full):
            entries.append(name)
    return sorted(entries)


def main():
    if len(sys.argv) > 1:
        print("This script uses the params file and does not accept command line arguments.")
        sys.exit(1)

    print("🚀 Starting Fabric notebook deployment...")

    workspace_id = os.environ.get("FABRIC_WORKSPACE_ID")
    token = os.environ.get("FABRIC_ACCESS_TOKEN") or os.environ.get("AZURE_ACCESS_TOKEN")
    if not workspace_id or not token:
        print("❌ Set FABRIC_WORKSPACE_ID and FABRIC_ACCESS_TOKEN/AZURE_ACCESS_TOKEN before running this script.")
        sys.exit(1)

    client = NotebooksClient(workspace_id, token)

    try:
        existing_list = client.get_notebooks()
        existing = {nb.get('displayName'): nb for nb in existing_list}
        print(f"📋 Found {len(existing_list)} existing notebooks in workspace")
    except Exception as e:
        print(f"⚠️  Warning: Could not list existing notebooks: {e}")
        existing = {}

    if not os.path.exists(NOTEBOOKS_DIR_DEFAULT):
        print(f"Notebook directory not found: {NOTEBOOKS_DIR_DEFAULT}")
        sys.exit(1)

    notebooks = discover_notebook_files(NOTEBOOKS_DIR_DEFAULT)

    deployed = 0
    skipped = 0
    failed = 0

    for nb in notebooks:
        nb_path = os.path.join(NOTEBOOKS_DIR_DEFAULT, nb)
        display_name = get_notebook_display_name(nb)
        print(f"-> Processing notebook: {display_name}")
        try:
            content = load_notebook_content(nb_path)
        except Exception as e:
            print(f"   ✗ Error reading notebook content: {e}")
            failed += 1
            continue

        existing_nb = client.get_notebook_by_name(display_name)
        if existing_nb:
            print(f"   → Updating notebook: {display_name}")
            client.update_notebook(existing_nb.get('id') or existing_nb.get('workspaceId') or existing_nb.get('itemId'), content)
            deployed += 1
            print(f"   ✓ Updated: {display_name}")
            continue

        try:
            print(f"   → Creating notebook: {display_name}")
            client.create_notebook(display_name, content)
            deployed += 1
            print(f"   ✓ Deployed: {display_name}")
        except Exception as e:
            print(f"   ✗ Failed to deploy {display_name}: {e}")
            failed += 1

    print(f"\nSummary: deployed={deployed}, skipped={skipped}, failed={failed}")


if __name__ == '__main__':
    main()
