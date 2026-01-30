#!/usr/bin/env bash
set -euo pipefail

# cleanup_sensitive.sh
# Usage:
#   ./scripts/cleanup_sensitive.sh      # list sensitive files
#   ./scripts/cleanup_sensitive.sh --delete  # delete found sensitive files (prompt before each)

DELETE=false
if [ "${1:-}" = "--delete" ]; then
  DELETE=true
fi

echo "Searching for common sensitive/unnecessary files..."

PATTERNS=(
  "sp.json"
  "publish-profile.xml"
  "*.publishsettings"
  "*.pem"
  "*.pfx"
  ".env"
  ".env.*"
  "app.zip"
  "*.zip"
  "*.log"
)

FOUND=()
while IFS= read -r -d $'\0' file; do
  FOUND+=("$file")
done < <(find . -type f \( $(printf -- '-name "%s" -o ' "${PATTERNS[@]}") -false \) -not -path './.git/*' -print0 || true)

if [ ${#FOUND[@]} -eq 0 ]; then
  echo "No matching files found."
  exit 0
fi

echo "Found the following files:"
for f in "${FOUND[@]}"; do
  echo "  $f"
done

if [ "$DELETE" = true ]; then
  echo
  echo "Deleting files (prompt before each)..."
  for f in "${FOUND[@]}"; do
    read -p "Delete $f? [y/N] " yn
    case "$yn" in
      [Yy]* ) rm -v "$f" || true; git rm -f --quiet "$f" || true ;;
      * ) echo "Skipping $f" ;;
    esac
  done
  echo "Deletion complete. Consider committing the deletions and verifying no secrets remain committed."
else
  echo
  echo "Run with --delete to interactively remove these files. Example:"
  echo "  ./scripts/cleanup_sensitive.sh --delete"
fi
