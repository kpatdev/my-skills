---
name: memo
description: Operate Apple Notes and Apple Reminders through the memo CLI on macOS. Use when the user asks to inspect or change either app, or asks to use memo for notes or reminders.
---

# memo

Treat every indexed change as an **attended transaction**: resolve the target from the list printed by the same live command, feed its number only after the line still matches, then verify the postcondition.

## Establish the command surface

Run:

```sh
command -v memo
memo --version
memo notes --help
memo rem --help
```

This skill is verified against memo 0.6.0 and 0.6.1 on macOS. For another version, use its installed `--help` output and the matching [upstream release source](https://github.com/antoniorodr/memo); use the [documentation](https://antoniorodr.github.io/memo/Getting%20started/) for orientation. Proceed when `memo` exists and every required flag appears in the installed help.

## Resolve notes through a snapshot

`memo notes` assigns each note a global number and caches that map in `~/.cache/memo/notes_cache.json` for 300 seconds. Memo's own note writes clear the cache; changes from Notes.app do not. Use `-nc` to rebuild the snapshot before resolving a target.

```sh
memo notes -nc                 # fresh global snapshot
memo notes -nc -f "Docs"       # discovery filter; global numbers remain
memo notes -v 12               # body as Markdown
memo notes -fl                 # exact folder and subfolder names; use alone
```

`-f` is a substring match over `Folder - Title`, not an exact folder selector. It can match a title or several similarly named folders. Use `memo notes -fl` to establish the exact folder name.

Memo 0.6.x can reject a displayed global number—or select the wrong note—when `-f` is combined with `-e`, `-d`, or `-m`. Use filters only for discovery; run indexed mutations unfiltered.

For non-interactive search, filter the listing:

```sh
memo notes -nc | rg -i -- 'invoice'
```

`memo notes -s` launches full-screen `fzf`; reserve it for a human-controlled terminal.

## Read

- List notes with `memo notes -nc`, optionally adding `-f` for discovery.
- Read a note only after matching its exact `N. Folder - Title` line; then run `memo notes -v N` against that snapshot.
- Run `memo rem` to list incomplete reminders. Reminders are fetched live and are not cached.

A read is complete when the requested content and its identifying note or reminder line are both visible.

## Change

Before any create, edit, move, delete, complete, reschedule, or export, read [`RECIPES.md`](RECIPES.md) for that operation's exact prompt order and loss risks. Then run this transaction:

1. **Inspect.** Refresh notes with `-nc`, or list reminders live. Quote the exact target line. For a note edit, move, or delete, also show `memo notes -v N`.
2. **Stage.** Prepare the complete new body or every prompt value. State the material effect and every operation-specific loss risk from `RECIPES.md`.
3. **Authorize.** Show the command, target, and staged values verbatim; get the user's explicit final OK.
4. **Re-resolve.** Start the mutation as a live process with stdin still open. For an indexed change, wait for its current list and selection prompt. Feed `N` only when the current `N. …` line is the authorized target. Return to step 1 on any mismatch.
5. **Execute.** Feed later prompts in the documented order. Capture the exit status and output.
6. **Verify.** Re-list notes with `-nc`, view the changed note, or re-list reminders. Compare the result with the staged postcondition.

The transaction is complete only when the exact postcondition is visible. A command error, target mismatch, or unverifiable result leaves it incomplete and must be reported without claiming success.

## Automation permission

An AppleScript error containing `-1743` or “Not authorized” means macOS has not granted the terminal automation access. Ask the user to enable the relevant terminal under **System Settings → Privacy & Security → Automation** for Notes or Reminders, then rerun the interrupted read or transaction from its first step.
