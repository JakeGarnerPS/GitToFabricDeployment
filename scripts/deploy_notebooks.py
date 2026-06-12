#!/usr/bin/env python3
"""
Deploy Notebooks to Microsoft Fabric
This script uploads notebook files directly to a Fabric workspace using medallion.notebooks helpers.
"""

import os
import sys
import argparse
from typing import List, Optional
from pathlib import Path

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
    parser = argparse.ArgumentParser(
        description="Deploy notebooks to Microsoft Fabric",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--workspace-id", required=True, help="Fabric workspace ID")
    parser.add_argument("--token", required=True, help="Azure access token")
    parser.add_argument("--notebook-dir", default=NOTEBOOKS_DIR_DEFAULT, help="Directory containing notebook files")
    parser.add_argument("--skip-existing", action="store_true", help="Skip notebooks that already exist in the workspace")

    args = parser.parse_args()

    print("🚀 Starting Fabric notebook deployment...")

    client = NotebooksClient(args.workspace_id, args.token)

    try:
        existing_list = client.get_notebooks()
        existing = {nb.get('displayName'): nb for nb in existing_list}
        print(f"📋 Found {len(existing_list)} existing notebooks in workspace")
    except Exception as e:
        print(f"⚠️  Warning: Could not list existing notebooks: {e}")
        existing = {}

    if not os.path.exists(args.notebook_dir):
        print(f"Notebook directory not found: {args.notebook_dir}")
        sys.exit(1)

    notebooks = discover_notebook_files(args.notebook_dir)

    deployed = 0
    skipped = 0
    failed = 0

    for nb in notebooks:
        nb_path = os.path.join(args.notebook_dir, nb)
        display_name = get_notebook_display_name(nb)
        print(f"-> Processing notebook: {display_name}")
        try:
            content = load_notebook_content(nb_path)
        except Exception as e:
            print(f"   ✗ Error reading notebook content: {e}")
            failed += 1
            continue

        existing_nb = client.get_notebook_by_name(display_name)
        if existing_nb and args.skip_existing:
            print(f"   → Skipping existing notebook: {display_name}")
            skipped += 1
            continue

        try:
            if existing_nb:
                print(f"   → Updating notebook: {display_name}")
                client.update_notebook(existing_nb.get('id') or existing_nb.get('workspaceId') or existing_nb.get('itemId'), content)
            else:
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
