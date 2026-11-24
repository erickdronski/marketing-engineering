---
name: "seo-aeo"
role: "channel"
description: "Prepare a page that answers a specific customer question and can be checked against source material."
status: "active"
actions:
  - "update_page"
---

# Search and answer-engine content

Start with an observed customer question and the current page. Read the offer and source notes. Ask research for a verified answer, drafting for the lead and supporting copy, and tracking for the current measurement window. Specify the page the owner intends to update. Avoid promising search rank or inclusion in an AI answer.

Save the proposed copy under `drafts/` and use `mktgkit queue submit <draft.md>` with channel `seo-aeo` and action `update_page`. Include cited claim IDs and the page owner. A person authorizes the edit before an external operator updates the page.
