# Decide what can run

Assign permissions to an **action and channel together** in `permissions.json`. A review decision for one publishing destination carries no permission for another.

| Mode | What happens |
|---|---|
| `draft_only` | A reviewer approves the item, a person performs the action and the team records the receipt. The gate returns 4 to an automation. This is the default for unlisted pairs. |
| `approve_each` | The gate accepts the current version of an approved item when its body, review metadata, dependencies and cited claims still qualify. Pending review returns 3. |
| `auto` | The gate may also accept unchanged, submitted text without an individual approval. The existing checks still run. A pair marked as spend cannot use this mode. |

From a client workspace, inspect the current rules and the verdict for one item.

```sh
mktgkit gate status --format json
mktgkit gate check --item Q-0001
```

The gate returns 0 for an eligible item. An ineligible or changed item returns a nonzero status with a reason. Already-live and withdrawn items cannot be sent again. There is no outgoing API call.

## Promote based on recorded work

Before moving from `draft_only` to `approve_each`, look for distinct approved items for the same pair that someone recorded as live. Moving to `auto` requires a recent, unbroken run of attended first-version approvals for that pair. Send-backs, incidents, second-version approvals and attendance overrides interrupt the run. The starter configuration uses three live items for the first change, then ten clean approvals inside thirty days for the second. Set thresholds to the client's review capacity and exposure.

```sh
mktgkit gate promote --action publish_post --channel content
mktgkit gate demote --action publish_post --channel content --reason "The offer changed; resume individual review."
```

Promotion needs a reviewer. Any operator can reduce autonomy. Use an individual reviewer name and keep the ledger in client-controlled version history. Reviewer names are asserted. An interactive terminal and absence of configured agent indicators are attendance signals. An explicit attendance override requires a reason that remains in the ledger. Someone with write access can alter the underlying files. Use independent change review for sensitive workspaces.

## Check a future connector

An adapter should pass the **exact final body** to `gate check --action publish_post --channel content` on standard input immediately before publishing. Stop on any nonzero result. Keep a delivery receipt keyed to the item and version. Every retry must check the publishing system's receipt first. Two separate systems can race between the permission check and delivery, so build provider-side deduplication before enabling unattended sends.

A Claude Code PreToolUse hook can do the read-only check for an explicitly mapped tool. Put a mapping under `tools` in `permissions.json` using the actual tool name and input field from the operator’s connector. Here is a fictional schema example.

```json
{
  "example_publish_post": {
    "action": "publish_post",
    "channel": "content",
    "content_field": "post.text"
  }
}
```

Run `mktgkit gate hook --print-settings` to see the hook settings for the configured names. Review and merge that snippet with the client's existing settings, make the installed command available to the hook, and verify it resolves the intended workspace. The hook blocks a mapped tool when its content is missing, ambiguous, changed or ineligible. Other tool names pass through. Tests exercise representative tool payloads locally. Run independent acceptance tests for each real connector and keep spending decisions with a person.
