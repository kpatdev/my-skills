---
name: cliproxy-quota
description: Check live remaining 5-hour and weekly quotas, and reset times, for every Claude and Codex OAuth account in the user's CLIProxyAPI instance. Use when asked about Claude/Codex usage, rate limits, remaining quotas, or which account has capacity.
---

# CLIProxyAPI quota check

Run a **single shell command** using `bash`, `curl`, and `jq`. No separate script, installable program, inference call, or plugin is needed.

- CLIProxyAPI management URL: `http://docker-ai:8317/v0/management`
- Authenticate using the **management key**, not a model/inference API key.
- Get the key from `CLIPROXY_MANAGEMENT_KEY`, or from `~/.config/cliproxy-quota/key` if it exists. If neither exists, ask the user to configure the key securely before running this command. Never put the key in the skill, console output, source control, or a command's literal arguments.
- This command must run on a device that can resolve and reach `docker-ai` on the user's Tailscale network.

## Check all accounts

Execute the whole block, without substituting a hardcoded management key:

```bash
set -euo pipefail
BASE='http://docker-ai:8317/v0/management'
KEY="${CLIPROXY_MANAGEMENT_KEY:-}"
if [[ -z "$KEY" && -r "$HOME/.config/cliproxy-quota/key" ]]; then
  KEY="$(<"$HOME/.config/cliproxy-quota/key")"
fi
if [[ -z "$KEY" ]]; then
  echo 'Missing CLIProxyAPI management key: set CLIPROXY_MANAGEMENT_KEY or ~/.config/cliproxy-quota/key' >&2
  exit 1
fi

accounts=$(curl -fsS --connect-timeout 5 --max-time 15 \
  -H "Authorization: Bearer $KEY" "$BASE/auth-files")
jq -e '.files | type == "array"' >/dev/null <<<"$accounts" || {
  echo 'Unexpected CLIProxyAPI auth-files response' >&2
  exit 1
}

jq -c '.files[] | select(.provider == "claude" or .provider == "codex")
  | {name, provider, auth_index,
     account_id:(.account_id // .chatgpt_account_id // .metadata.account_id // .metadata.chatgpt_account_id // "")}' <<<"$accounts" |
while IFS= read -r account; do
  name=$(jq -r '.name // "unknown"' <<<"$account")
  provider=$(jq -r '.provider' <<<"$account")
  idx=$(jq -r '.auth_index // empty' <<<"$account")
  if [[ -z "$idx" ]]; then
    printf '%s: missing auth_index\n' "$name"
    continue
  fi

  if [[ "$provider" == 'claude' ]]; then
    payload=$(jq -nc --arg idx "$idx" '{
      auth_index:$idx, method:"GET",
      url:"https://api.anthropic.com/api/oauth/usage",
      header:{"Authorization":"Bearer $TOKEN$","anthropic-beta":"oauth-2025-04-20"}
    }')
  else
    aid=$(jq -r '.account_id' <<<"$account")
    # Some versions omit the Codex account ID from auth-files. Extract only
    # the ID from the auth-file download, never print or save its tokens.
    if [[ -z "$aid" ]]; then
      aid=$(curl -fsSG --connect-timeout 5 --max-time 15 \
        -H "Authorization: Bearer $KEY" \
        --data-urlencode "name=$name" "$BASE/auth-files/download" 2>/dev/null \
        | jq -r '.account_id // .chatgpt_account_id //
            (.id_token | if type == "object" then .chatgpt_account_id else null end) //
            empty' 2>/dev/null) || aid=''
    fi
    payload=$(jq -nc --arg idx "$idx" --arg aid "$aid" '{
      auth_index:$idx, method:"GET",
      url:"https://chatgpt.com/backend-api/wham/usage",
      header:({
        "Authorization":"Bearer $TOKEN$",
        "User-Agent":"codex_cli_rs/0.76.0"
      } + (if $aid == "" then {} else {"Chatgpt-Account-Id":$aid} end))
    }')
  fi

  if ! response=$(curl -fsS --connect-timeout 5 --max-time 30 \
    -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
    -d "$payload" "$BASE/api-call"); then
    printf '%s (%s): quota API request failed\n' "$name" "$provider"
    continue
  fi

  jq -r --arg name "$name" --arg provider "$provider" '
    def percent($n): (((100 - $n) * 10 | round) / 10 | tostring) + "% remaining";
    def reset($v): if ($v|type) == "number" then $v|todateiso8601
      elif ($v|type) == "string" and $v != "" then $v
      else "unknown" end;
    def window($label; $w; $field):
      if ($w|type) == "object" and ($w[$field]|type) == "number" then
        "  \($label): \(percent($w[$field])); resets \(reset($w.reset_at // $w.resets_at))"
      else "  \($label): unavailable" end;
    def duration($w; $fallback):
      if $w.limit_window_seconds == 18000 then "5-hour"
      elif $w.limit_window_seconds == 604800 then "7-day"
      else $fallback end;
    (if (.body|type) == "string" then (try (.body|fromjson) catch {}) else (.body // {}) end) as $body |
    "\($provider | ascii_upcase) | \($name)",
    (if (.status_code // 0) != 200 then
       "  Quota endpoint failed: HTTP \(.status_code // "unknown")"
     elif $provider == "claude" then
       window("5-hour"; $body.five_hour; "utilization"),
       window("7-day"; $body.seven_day; "utilization"),
       ( ["seven_day_opus", "seven_day_sonnet"][] as $k
         | if $body[$k] != null then
             window(($k | sub("seven_day_"; "") | ascii_upcase) + " 7-day"; $body[$k]; "utilization")
           else empty end )
     else
       window(duration($body.rate_limit.primary_window; "primary");
              $body.rate_limit.primary_window; "used_percent"),
       window(duration($body.rate_limit.secondary_window; "secondary");
              $body.rate_limit.secondary_window; "used_percent")
     end)
  ' <<<"$response"
done
unset KEY
```

## Report results

- Show **each account separately** and give **remaining percentage**, not used percentage, for 5-hour and weekly windows.
- Convert timestamps to the user's local time zone when reporting; the shell output may contain UTC timestamps. A numerical Codex `reset_at` is Unix seconds.
- Label Codex windows `5-hour` or `7-day` only if `limit_window_seconds` equals 18000 or 604800. Otherwise use `primary` / `secondary`.
- Treat missing values and failed requests as **unknown**, never as zero remaining. Do not add remaining percentages across accounts.
- These calls retrieve quota data; they do not submit model prompts. The provider usage endpoints can change.
- Never print the management key or raw auth-file downloads. Never store OAuth tokens.

## Optional secure key setup

The user can provide the key via their terminal without putting it into their shell history:

```bash
mkdir -p ~/.config/cliproxy-quota
chmod 700 ~/.config/cliproxy-quota
read -rsp 'CLIProxyAPI management key: ' key; echo
printf '%s' "$key" > ~/.config/cliproxy-quota/key
chmod 600 ~/.config/cliproxy-quota/key
unset key
```

This optional local key file is **not** part of the skill. If the user prefers environment variables, `CLIPROXY_MANAGEMENT_KEY` takes precedence.
