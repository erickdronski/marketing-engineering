# Running this marketing workspace

Begin with `goals.md`. Name the goal, audience and channel in each brief. Read the relevant offer, customer, brand and claim notes in `brain/`. Record the source and date for outside research. Treat assumptions as open questions.

The orchestrator assigns deliverables in `batches/`. Channel owners prepare one draft per action in `drafts/`, cite signed claims, and submit it to the review queue. A reviewer returns concrete edits or approves the exact version. If the copy changes, submit the revised text for another review.

Use the warehouse to investigate outcomes. Carry source dates, numerator, denominator and missing attribution into a report. If required inputs are stale, refresh them before making the decision. Keep unsent drafts, approvals, external delivery receipts and observed outcomes distinct.

## Who operates each part

- The orchestrator owns the batch brief and dependencies. The active channel owners own their queue items.
- Research, draft, visuals and tracking specialists return evidence or artifacts to a channel owner. They have no authority to approve claims, publish, spend or promote a permission.
- A named client reviewer approves claims, decides on queue items and changes operating permissions. Open a real terminal for those decisions.
- An operator uses the approved destination outside the toolkit and records its delivery reference. Run `mktgkit gate check --item Q-0001` with the actual item ID before a connected send. The toolkit performs no external send.

See `permissions.json` for each channel and action. The templates ship with no external tool mappings. Only mapped tools can be checked by a configured hook. File ownership, client account permissions and independent review matter when automating delivery.
