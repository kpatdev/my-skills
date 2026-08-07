# Recipes

Each recipe assumes a fresh **snapshot** and an explicit OK from the user — see "Mutating" in `SKILL.md`. `$MEMO_EDITOR` is the absolute path to `scripts/memo-editor.sh`.

## Edit a note — `-e`

The shim overwrites the editor's temp file wholesale, so build the full new body first:

```sh
memo notes -v 12 > /tmp/note.md      # exact current body
# ...rewrite /tmp/note.md in full...
printf '12\n' | MEMO_BODY=/tmp/note.md EDITOR="$MEMO_EDITOR" memo notes -e
```

`-v` renders each inline image as a `[MEMO_IMG_1]` placeholder — the same placeholders the editor would have shown. Carry one through verbatim to keep that image; drop it to delete the image. Surviving images are re-attached at the end of the note regardless of where the placeholder sat, an AppleScript limitation with no workaround.

If the body comes back byte-identical, `memo` prints "No changes made" and writes nothing.

## Move a note — `-m`

```sh
printf '12\nArchive\n' | memo notes -m      # number, then target folder
```

A target folder that doesn't exist is **created**, so a typo silently makes a stray folder — check `memo notes -fl` first. The move re-creates the note from its name and body and deletes the original: the note gets a new id, and anything not carried in the body (attachments) may not survive.

## Delete a note — `-d`

```sh
printf '12\n' | memo notes -d
```

## Delete a folder — `-r`

```sh
printf 'Old Stuff\n' | memo notes -r        # folder name, not a number
```

Takes every note in the folder with it. The only confirmation is the one you feed it, so get the user's OK on the folder name spelled out.

## Export to HTML — `-ex`

```sh
printf 'y\ny\n' | memo notes -ex                 # all notes → ~/Desktop/notes/
printf 'y\ny\n' | memo notes -ex -f "Docs"       # one folder
printf 'y\nn\n/Users/you/exports\n' | memo notes -ex   # custom path
```

A custom path must already exist — `memo` prints an error but still proceeds when it doesn't. Create the directory first.

## Reminders — `memo rem`

Reminders are fetched live, never cached, and the list covers incomplete reminders only. There's no list or folder filter. `-c`, `-d`, and `-e` each print the full numbered list and then prompt, so the numbers you read are the numbers they use; an out-of-range number raises `IndexError` and changes nothing.

```sh
printf 'Call Denise\n2026-08-12\n09:00\n' | memo rem -a   # title, YYYY-MM-DD, HH:MM
printf '4\n' | memo rem -c                                # complete
printf '4\n' | memo rem -d                                # delete
printf '4\ntitle\nNew title\n' | memo rem -e              # retitle
printf '4\ndue date\n2026-08-12\n09:00\n' | memo rem -e   # reschedule
```

All three fields are required on add — there's no way to create an undated reminder. Reminder titles go into AppleScript unescaped, so a `"` in a title breaks the command; use plain titles, or say so and let the user add the quotes in Reminders.app.
