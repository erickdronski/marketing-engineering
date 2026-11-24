# Set up one client

Create a separate workspace for each client. The `init` command accepts a new or empty directory and leaves populated destinations alone. A blank workspace contains role definitions, empty CSV headers, operating policies and room for evidence. The `--example` option loads Wrenfield’s synthetic records and pinned clock.

| Location | Put this here |
|---|---|
| `goals.md` | The business question, counting rule, data source, target and review date. |
| `batches/` | A brief with an accountable owner, dependencies and a definition of done for each deliverable. |
| `agents/` | Assignments for the orchestrator, channel owners and specialists. Read these as job descriptions in any agent harness. |
| `brain/` | Sourced facts, inferences, assumptions, claim sign-offs, reusable edits and result notes. |
| `drafts/` and `queue/` | Proposed work and its review state. Keep approval and delivery distinct. |
| `log/ledger.jsonl` | The decision history. Client permissions and independent review protect the source of record. |
| `warehouse/seed/` | Client-controlled exports with stable IDs. Record their extraction times in the load log. |

For a practice engagement, create an example workspace, inspect its four queue items and open its static board. For a real engagement, replace the starter goal, document a source, choose a reviewer and get one manual run accepted before wiring an adapter. The operator and the client reviewer should have different credentials in the live systems.

Run `mktgkit check -w client-work` after editing the workspace. Warnings call attention to stale evidence or an unbuilt warehouse. Errors such as a broken link or a changed approval need correction. Use `--format json` when another program consumes the output. CLI commands work on a local filesystem. Keep a shared client workspace under ordinary source control with reviewed changes and a named operator; a live synced folder is unsuitable for its lock and database.
