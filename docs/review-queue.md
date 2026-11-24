# Run a marketing review

Use one queue item per destination and action. A product page and a social post can share evidence while carrying distinct copy, owners and approvals. The person reviewing the item should be able to answer three questions. Who is the audience? What exact text will they see? Which source supports each measurable claim?

## Submit the first draft

From an installed Wrenfield example workspace, inspect the existing queue and its evidence.

```sh
mktgkit queue list
mktgkit queue show Q-0002
mktgkit claims list
mktgkit queue render --out out/queue.html
```

Open the HTML file locally to read the drafts and their latest recorded decisions. Keep client drafts and reports inside a client-controlled workspace.

For your own active content channel, save this example as `drafts/booking-post.md`. The copy asks a reader to do one thing. It makes no numerical performance claim.

```markdown
---
title: Request a site visit
channel: content
action: publish_post
priority: medium
claims: []
depends_on: []
---
Planning a new service route? Send the dispatcher your service area and request a site visit.
```

```sh
mktgkit claims check drafts/booking-post.md
mktgkit queue submit drafts/booking-post.md
```

Use the item ID printed by submit. In the commands below, replace `Q-0001` with that ID. A rejected submission leaves the draft file available for editing.

## Trace a figure to its source

Record the figure, measurement period, population, source and evidence owner under `brain/claims/`. Give the note a unique ID, a specific source for a fact or a documented derivation for an inference, and an expiry date when appropriate. The reviewer checks the underlying evidence before running `mktgkit claims approve C-001` in their own terminal. List that ID in the draft’s `claims` header.

The check recognizes currencies, percentages, multipliers, magnitude suffixes and time units. It normalizes equivalent spellings such as “38 percent” and “38%”. An unsupported figure, expired endorsement, changed source note or banned brand phrase stops the draft. A reviewer still needs to examine the meaning. A measured percentage for one service region cannot justify promising the same result for every customer. Plain counts and numbers written as words require manual review.

## Return a draft for revision

A reviewer sends one specific change, optionally naming a source note that future drafts should consult.

```sh
mktgkit queue send-back Q-0001 --feedback "Replace the opening question with the dispatcher's next step." --because "The reader has already requested a route." --applies-to voice
```

The ledger records the decision. The edit note under `brain/edits/` retains the instruction and links it to its draft. Edit the source draft, then submit the new version.

```sh
mktgkit queue resubmit Q-0001 drafts/booking-post.md
mktgkit queue approve Q-0001 --by reviewer
mktgkit gate check --item Q-0001
```

Only an approved or returned item can be resubmitted. Its previous approval expires when its version changes. Each dependency must already be approved or live before approval. When an approved draft’s text has been edited directly in the queue, restore it or use resubmit to start a new review.

## Record delivery and corrections

The client or their publishing system performs the action. Record its actual receipt afterward. Replace the example URL with the live item’s URL.

```sh
mktgkit queue mark-live Q-0001 --url https://example.org/booking
mktgkit queue incident Q-0001 --note "The live link pointed to last season's booking form."
```

An incident flags the item. If its action and channel currently have automatic permission, their mode drops to per-item approval. Record the correction under a fresh review. To abandon a draft prior to delivery, use `mktgkit queue withdraw Q-0001 --reason "The offer has ended."`

See the [permission rules](permissions.md) for the difference between `draft_only`, `approve_each` and `auto`.
