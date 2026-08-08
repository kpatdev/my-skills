#!/bin/sh
# Replace memo's editor file with a staged, non-empty Markdown body.
# Copy through a sibling temporary so a failed copy leaves memo's file intact.

target=$1

if [ -z "$target" ]; then
  echo "memo-editor: memo did not pass an editor file" >&2
  exit 1
fi

if [ -z "$MEMO_BODY" ]; then
  echo "memo-editor: set MEMO_BODY to a staged Markdown file" >&2
  exit 1
fi

if [ ! -r "$MEMO_BODY" ] || [ ! -s "$MEMO_BODY" ]; then
  echo "memo-editor: MEMO_BODY must be readable and non-empty ($MEMO_BODY)" >&2
  exit 1
fi

staged_target=$(mktemp "${target}.memo-editor.XXXXXX") || exit 1
trap 'rm -f "$staged_target"' EXIT HUP INT TERM

if ! cp "$MEMO_BODY" "$staged_target"; then
  echo "memo-editor: failed to stage MEMO_BODY" >&2
  exit 1
fi

if ! mv -f "$staged_target" "$target"; then
  echo "memo-editor: failed to replace memo's editor file" >&2
  exit 1
fi

trap - EXIT HUP INT TERM
