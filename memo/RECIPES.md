# Operation recipes

Use these only inside the transaction in [`SKILL.md`](SKILL.md). `$memo_editor` below means the absolute path to `scripts/memo-editor.sh` in this skill.

Memo 0.6.x interpolates prompted folder names and reminder titles into AppleScript without escaping literal double quotes. Use names without `"` for mutations; use Notes.app or Reminders.app when quotes are required.

## Create a note

Confirm the destination's exact spelling with `memo notes -fl`. Stage the body in a private temporary file; its first rendered line becomes the note title.

```sh
memo_editor="/absolute/path/to/memo/scripts/memo-editor.sh"
memo_body_file=$(mktemp -t memo-body)
chmod 600 "$memo_body_file"
printf '%s\n' '# Grocery list' '' '- milk' '- eggs' > "$memo_body_file"
MEMO_BODY="$memo_body_file" EDITOR="$memo_editor" memo notes -f "Docs" -a
```

The shim requires a non-empty body and leaves memo's editor file unchanged on failure, so memo cancels safely. Remove the staged file after verification.

Memo 0.6.x inserts converted HTML directly into an AppleScript string. Plain Markdown prose, headings, lists, emphasis, and code are safe; Markdown links, images, and raw HTML attributes produce literal double quotes and can make the write fail. Use plain URLs or Notes.app when the body needs those constructs.

## Edit a note

Editing replaces the complete note body. Build a complete replacement file from the content itself; `memo notes -v N` adds presentation whitespace around its output, so do not redirect it verbatim into the replacement.

Before authorization, explain the 0.6.x round-trip losses:

- Apple Notes semantic styles and linked-text URLs can be lost.
- Non-image attachments can be lost.
- Images appear as `[MEMO_IMG_N]` placeholders. Keep each required placeholder verbatim; surviving images are reattached at the end of the note. Removing a placeholder deletes that image.

Prefer Notes.app when any loss is unacceptable. Otherwise, stage the full replacement in `$memo_body_file`, then start this command as a live process:

```sh
MEMO_BODY="$memo_body_file" EDITOR="$memo_editor" memo notes -nc -e
```

Wait for the fresh unfiltered list and edit prompt, match the authorized line, then feed its global number. If the stripped replacement equals the original Markdown, memo writes nothing.

## Move a note

Confirm the exact destination with `memo notes -fl`, then start `memo notes -nc -m` as a live process. Match and feed the authorized global number, then feed the destination folder.

A nonexistent destination is created, so a typo creates a stray folder. A move creates a new note from the original name and HTML body and deletes the original; its ID changes and attachments may not survive. Include both effects in the authorization.

## Delete a note or folder

- Note: start `memo notes -nc -d`, match the authorized line, then feed its global number.
- Folder: start `memo notes -r`, wait for its folder list and prompt, then feed the exact authorized folder name.

Folder deletion also deletes every note it contains. Memo does not clear the notes cache after folder deletion, so verification must use `memo notes -nc`. Deleted Notes content normally goes to Recently Deleted, where Apple controls the recovery window.

## Export notes

State the destination and possible overwrites before authorization. Existing same-name `.html` and `.md` files can be truncated. Password-protected notes are skipped, and Markdown conversion does not preserve pictures or attachments.

Prompt order is: confirm export, choose default path, enter a custom path when needed, then choose Markdown conversion. Feed all prompts:

```sh
printf 'y\ny\nn\n' | memo notes -ex                    # all → default, HTML only
printf 'y\ny\ny\n' | memo notes -ex -f "Docs"          # folder → default, HTML + Markdown
printf 'y\nn\n/Users/you/exports/\nn\n' | memo notes -ex  # all → custom, HTML only
```

Create a custom destination first. Memo 0.6.x reports a missing path, then proceeds to create it, which can disguise a typo.

## Reminders

`memo rem` lists incomplete reminders across all reminder lists; memo 0.6.x has no reminder-list filter. It shows an undated reminder as due today. Every added reminder requires a title, date, and time:

```sh
printf '%s\n' 'Call Denise' '2026-08-12' '09:00' | memo rem -a
```

For an indexed reminder change, start the command as a live process and keep stdin open:

- Complete: `memo rem -c`; match the fresh line, then feed `N`.
- Delete: `memo rem -d`; match the fresh line, then feed `N`.
- Retitle: `memo rem -e`; match and feed `N`, then `title`, then the new title.
- Reschedule: `memo rem -e`; match and feed `N`, then `due date`, `YYYY-MM-DD`, then `HH:MM`.

The live list matters because reminders have no cached snapshot. Feed the number only after the command's current line still matches the authorized target.
