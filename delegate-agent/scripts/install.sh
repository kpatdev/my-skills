#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
COMMON_ROOT="${HOME}/.agents/skills"
COMMON_DEST="${COMMON_ROOT}/delegate-agent"
CLAUDE_ROOT="${HOME}/.claude/skills"
CLAUDE_DEST="${CLAUDE_ROOT}/delegate-agent"

mkdir -p "$COMMON_ROOT" "$CLAUDE_ROOT"

if [[ "$SOURCE_DIR" != "$COMMON_DEST" ]]; then
  if [[ -e "$COMMON_DEST" || -L "$COMMON_DEST" ]]; then
    echo "Refusing to replace existing $COMMON_DEST" >&2
    echo "Remove it manually if you want to reinstall." >&2
    exit 1
  fi
  cp -R "$SOURCE_DIR" "$COMMON_DEST"
fi

if [[ -e "$CLAUDE_DEST" && ! -L "$CLAUDE_DEST" ]]; then
  echo "Refusing to replace existing non-symlink $CLAUDE_DEST" >&2
  exit 1
fi
ln -sfn "$COMMON_DEST" "$CLAUDE_DEST"

chmod +x "$COMMON_DEST/scripts/delegate-agent" "$COMMON_DEST/scripts/delegate_agent.py" "$COMMON_DEST/scripts/install.sh"

echo "Installed canonical skill: $COMMON_DEST"
echo "Linked Claude skill:      $CLAUDE_DEST -> $COMMON_DEST"
echo "Codex, OpenCode, and Pi can discover ~/.agents/skills directly."
echo "Claude Code discovers the linked ~/.claude/skills copy."
