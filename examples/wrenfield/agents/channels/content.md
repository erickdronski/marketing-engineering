---
name: "content"
role: "channel"
description: "Prepare an evidence-backed post for one audience and submit the draft for review."
status: "active"
actions:
  - "publish_post"
---

# Content

Read the batch, offer, audience, brand voice and relevant approved claim notes. Ask research to check evidence, drafting to prepare one post, and visuals for a diagram or brief only if it clarifies the offer. Include the intended destination and call to action in the brief.

Write the asset under `drafts/` and use `mktgkit queue submit <draft.md>` with channel `content` and action `publish_post`. Wait for dependencies and reviewer decisions. Give tracking the queue ID and the published reference when the operator records delivery.
