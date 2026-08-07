#!/bin/sh
# Stands in for $EDITOR when driving `memo notes -a` / `memo notes -e`
# non-interactively.
#
# memo runs [$EDITOR, tempfile] directly — no shell, no word splitting — then
# imports whatever the temp file holds afterwards. This script copies the body
# you prepared in $MEMO_BODY over that temp file.
#
#   MEMO_BODY=/tmp/note.md EDITOR=/path/to/memo-editor.sh memo notes -f Docs -a
#
# On any error it leaves the temp file untouched, which memo reads as
# "cancelled" (on add) or "no changes made" (on edit).

target="$1"

if [ -z "$target" ]; then
  echo "memo-editor: no target file; memo passes it as \$1" >&2
  exit 1
fi

if [ -z "$MEMO_BODY" ]; then
  echo "memo-editor: set MEMO_BODY to a file holding the note body" >&2
  exit 1
fi

if [ ! -r "$MEMO_BODY" ]; then
  echo "memo-editor: cannot read MEMO_BODY ($MEMO_BODY)" >&2
  exit 1
fi

cat "$MEMO_BODY" > "$target"
