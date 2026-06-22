#!/usr/bin/env bash
# Refresh the CiteVyn source catalog from upstream feeds.
#
# Pulls the latest snapshot URLs from the configured upstream sources
# (e.g. Anthropic docs RSS, OpenAI docs sitemap, MCP server registry),
# stages them under db/seed/sources/, and prints a summary of what
# changed. It does NOT run ingestion or re-embed — that is the job of
# the `db.ingest.ingest_sources` worker, invoked separately via
# `make refresh`.
#
# This script is safe to run repeatedly. It is intentionally read-mostly
# on the local filesystem; the only network egress is to the upstream
# source registries. If the network is unreachable it exits 0 with a
# warning so the script is cron-safe.
#
# Run from anywhere; the script resolves its own repo root.
# Requirements: curl, jq, sha256sum.

set -Eeuo pipefail

# --- configuration --------------------------------------------------------

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCES_DIR="$REPO_ROOT/db/seed/sources"
MANIFEST="$SOURCES_DIR/.refresh-manifest.json"
TIMEOUT="${REFRESH_TIMEOUT:-30}"

mkdir -p "$SOURCES_DIR"

# --- helpers --------------------------------------------------------------

log()  { printf '\033[1;34m→\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# --- upstream registry ----------------------------------------------------
# Each entry is "<name> <manifest-url>". Keep this list short and curated.
# Sources that cannot be reached are skipped with a warning, not fatal.

UPSTREAMS=(
  "anthropic-docs https://docs.anthropic.com/en/release-notes/rss.xml"
  "openai-docs    https://platform.openai.com/docs/sitemap.xml"
  "mcp-servers    https://registry.modelcontextprotocol.io/v0.1/servers"
)

# --- per-source refresh ---------------------------------------------------
# This is the skeleton: for each upstream, fetch the manifest, compare its
# hash to the previous run, and stage a `.stale` marker if it changed.
# Ingesting the new content is delegated to the worker (out of scope here).

declare -i CHANGED=0
declare -i SKIPPED=0
declare -a NAMES=()

for entry in "${UPSTREAMS[@]}"; do
  name="${entry%% *}"
  url="${entry##* }"
  NAMES+=("$name")

  log "checking $name ($url)"
  body_file="$(mktemp -t "refresh-${name}.XXXXXX")"
  if ! curl --silent --show-error --max-time "$TIMEOUT" -o "$body_file" "$url"; then
    warn "  unreachable, skipping (network is optional for skeleton)"
    SKIPPED+=1
    rm -f "$body_file"
    continue
  fi

  size=$(wc -c < "$body_file" | tr -d ' ')
  hash=$(sha256sum "$body_file" | awk '{print $1}')

  prev_hash=""
  if [[ -f "$MANIFEST" ]]; then
    prev_hash=$(jq -r --arg n "$name" '.[$n].sha256 // ""' "$MANIFEST" 2>/dev/null || true)
  fi

  if [[ "$hash" != "$prev_hash" ]]; then
    log "  changed: $size bytes, sha256=${hash:0:12}…"
    CHANGED+=1
    touch "$SOURCES_DIR/${name}.stale"
  else
    log "  unchanged"
  fi

  rm -f "$body_file"
done

# --- write manifest -------------------------------------------------------

tmp_manifest="$(mktemp -t "refresh-manifest.XXXXXX.json")"
{
  echo "{"
  first=1
  for name in "${NAMES[@]}"; do
    marker="$SOURCES_DIR/${name}.stale"
    if [[ $first -eq 0 ]]; then echo ","; fi
    first=0
    printf '  %q: {"stale": %s}' "$name" \
      "$([[ -f $marker ]] && echo true || echo false)"
  done
  echo
  echo "}"
} > "$tmp_manifest"
mv "$tmp_manifest" "$MANIFEST"

# --- summary --------------------------------------------------------------

log "refresh complete: $CHANGED changed, $SKIPPED skipped (network)"
if (( CHANGED > 0 )); then
  log "run 'make refresh' to ingest the stale sources into the catalog."
fi
exit 0
