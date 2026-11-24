# Start a client workspace

This is a clean operating workspace. Add your client's goals, sources, reviewers and measures before starting a batch. The packaged starter contains no fictional client records or signed claims.

1. Agree on one decision and write its metric and source in `goals.md`. Set the reporting time zone and eligibility rules.
2. Add an offer, customer note and brand note to `brain/`. Preserve the source and date. Ask a named reviewer to verify any public figure.
3. Read `AGENTS.md` and `permissions.json` together. Choose a channel and create one batch. Assign a reviewer and identify where an operator would make the external change.
4. Gather an approved, de-identified extract if a report needs data. Record the source's actual load time. Run `mktgkit check` in this workspace.
5. Submit one draft to the queue and follow it through review before connecting a live system. The standalone toolkit works offline.

For the fictional project and worked example, open `examples/wrenfield/` in the source repository.

## Submit the first draft

In the workspace you initialized, save the following as `drafts/first-post.md`. Replace the question with copy the client wants to review. This first exercise needs no claim or warehouse data.

```markdown
---
title: First customer question
channel: content
action: publish_post
priority: low
---
What would help your team decide whether to book a consultation?
```

```sh
mktgkit queue submit drafts/first-post.md
mktgkit queue list
```

The item should appear in review. Open the corresponding Markdown file in `queue/` and trace its submission in `log/ledger.jsonl`. Complete a review in the client workspace before anyone uses the copy externally.
