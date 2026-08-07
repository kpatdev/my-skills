---
name: memo
description: Read and write Apple Notes and Reminders from the terminal with the memo CLI.
disable-model-invocation: true
---

# memo

`memo` is a macOS-only CLI over Apple Notes (`memo notes`) and Apple Reminders (`memo rem`). It was built for a human sitting at a TTY — it prompts, and it opens `$EDITOR`. Everything below is how to **drive** it from a non-interactive shell instead.

Check what you're working against; flags move between releases:

```sh
memo --version    # this skill is written against 0.6.0
```

## Drive it — never let it block

Every prompt `memo` shows is a plain stdin read, so feed it:

```sh
printf '3\n' | memo notes -f "Docs" -d
```

One command can't be driven: `memo notes -s` launches a full-screen `fzf` picker and never returns without a human at the keyboard. Search by listing instead:

```sh
memo notes | grep -i "invoice"
```

## The snapshot

`memo notes` prints one line per note — `N. Folder - Title`. That `N` is what every number prompt and `-v N` addresses.

- `N` is a global index over all your notes. `-f` filters which lines print but keeps the original numbers, so a number read off a filtered list stays valid.
- The list is cached in `~/.cache/memo/notes_cache.json` for 300 seconds. `memo`'s own writes clear it; edits made in Notes.app do not.

So the numbering is a **snapshot** of a moment: take it and act on it in the same breath. Prefix `-nc` to force a fresh one.

`-f` is a substring match against the whole `Folder - Title` string, not a folder lookup — `-f Doc` matches both `Docs` and `Documentation`, and `-f Tesla` matches a note titled "Tesla Copy" sitting in any folder. Get exact folder names from `memo notes -fl`.

Flags don't combine: `-fl` must be alone, `-a` requires `-f`, and only one of `-e -d -m -r -ex -v -s` per command.

## Reading

```sh
memo notes                # every note, numbered
memo notes -f "Docs"      # filtered; numbers preserved
memo notes -nc -f "Docs"  # ...from a fresh snapshot
memo notes -v 12          # note 12's body, as Markdown
memo notes -fl            # folder and subfolder names (must be alone)
memo rem                  # incomplete reminders, numbered, with due dates
```

Recently Deleted is excluded from every listing.

## Mutating

Every write runs this sequence. Don't compress it — the number you type is only as good as the snapshot it came from.

1. **Refresh the snapshot.** `memo notes -nc -f "<folder>"`.
2. **Read back the target.** Quote the exact `N. Folder - Title` line to the user. For a delete or an edit, show `memo notes -v N` too, so the content being changed is on screen.
3. **Show the command verbatim and get an explicit OK.** Name the blast radius when it's wider than one note — `-r` removes a folder *and every note in it*.
4. **Run it**, stdin fed.
5. **Verify.** Re-list with `-nc`, or `-v` the note. Done when the intended change is visible and nothing else moved.

Deleted notes land in Recently Deleted and are recoverable there for about 30 days. A deleted folder takes its notes down with it.

### Creating a note

`memo` opens `$EDITOR` on a temp Markdown file and imports whatever you leave in it. It runs `[$EDITOR, tempfile]` directly — never shell-split — so `$EDITOR` has to be one executable, not a command line. This skill ships a **shim** that stands in for the editor:

```sh
MEMO_EDITOR="<absolute path to this skill>/scripts/memo-editor.sh"

printf '# Grocery list\n\n- milk\n- eggs\n' > /tmp/note.md
MEMO_BODY=/tmp/note.md EDITOR="$MEMO_EDITOR" memo notes -f "Docs" -a
```

- Apple Notes takes the note's title from the first line of the body — open the file with it.
- The Markdown is converted to HTML before it reaches AppleScript, and `" < > &` are escaped along the way, so ordinary prose needs no special handling.
- An empty body, or an unset `MEMO_BODY`, leaves the placeholder in place and `memo` cancels the create.

## Everything else — `RECIPES.md`

[`RECIPES.md`](RECIPES.md) holds the stdin recipes for the rest: **editing** a note (including keeping its images), **moving** notes between folders, **deleting** notes and folders, **exporting** to HTML, and the full **reminders** set — add, complete, delete, retitle, reschedule. Open it whenever the task is one of those.

## When osascript refuses

An error mentioning `-1743` or "Not authorized" means macOS hasn't granted automation access to Notes or Reminders. That's a GUI consent dialog under System Settings → Privacy & Security → Automation — hand it to the user, it can't be granted from the shell.
