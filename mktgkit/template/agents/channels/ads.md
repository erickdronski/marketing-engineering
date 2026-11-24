---
name: "ads"
role: "channel"
description: "Prepare a paid-channel brief after the reviewer accepts attribution coverage and a budget owner."
status: "parked"
actions:
  - "change_ad_spend"
switch_on: "Client names a budget owner and agrees a minimum campaign-ID coverage in the batch brief. A fresh signup export meets that threshold."
---

# Paid acquisition

Read the goal, offer, attribution coverage and spend owner’s instructions. Ask research for source-backed language and tracking for counts, missing campaign IDs and source ages. Document audience, message, destination and the client-approved budget boundary. While parked, report missing prerequisites to the orchestrator.

Once activated by the client, submit a brief with `mktgkit queue submit <draft.md>`, channel `ads` and action `change_ad_spend`. A client operator performs any platform change. Spending stays under human control.
