# Measure campaign activity

A consultant can use the local warehouse to answer two questions before recommending more spend. Which campaigns produced recorded trial signups? How much of the available signup data can be attributed at all?

## Try the fictional example

From the repository root, build and query the Wrenfield example.

```sh
mktgkit warehouse build -w examples/wrenfield
mktgkit warehouse query "SELECT * FROM attribution_coverage" -w examples/wrenfield
mktgkit warehouse query "SELECT * FROM campaign_performance ORDER BY spend_usd DESC LIMIT 3" -w examples/wrenfield
```

The synthetic exports contain **125 signups**. **76** carry a campaign identifier (60.8%). The route-planning campaign records $1,001.20 in spend and 18 tagged signups, or $55.62 per tagged signup. At the example clock the spend export is 57 hours old, beyond its 26-hour limit. Refresh the export before acting on the ranking. These counts describe observed records. An experiment or another causal design would be needed to estimate incremental conversions.

## Load client exports

1. Initialize a separate workspace for each client. Each file under `warehouse/seed/` starts with the accepted header. Preserve the header and column order, save as UTF-8 CSV, and use an empty field for an unknown value.
2. Export sessions, signups, published-post statistics, daily campaign spend and email events at the grains below. Preserve stable source IDs across exports. Export only the columns required for analysis. Omit raw names, contact information and message bodies.
3. Replace each CSV with the complete snapshot you intend to analyze. Use one currency (USD in the supplied views). Align campaign IDs across sources. Leave the campaign field empty for unattributed sessions and signups.
4. Record each export in `load_log.csv` with its table name, actual source load timestamp in UTC, row count and origin. A rebuild retains the last good database if a file fails validation. Rebuilding alone does not refresh the source timestamps.
5. Run `mktgkit warehouse build -w CLIENT`. Then run `mktgkit warehouse freshness --require-fresh -w CLIENT`. A missing, future-dated or overdue load returns exit code 5. Edit `warehouse/freshness.json` to match each client's ingestion cadence.
6. Review coverage and gaps before using a campaign-level rate in a recommendation. The spend view joins totals after aggregating each source by campaign; this prevents one signup or session from multiplying spend. Unrecorded spend and cost with a zero denominator display as an em dash.

| Table | One row represents |
|---|---|
| web_sessions | One visit, keyed by session_id |
| posts | One published post with cumulative counts from one export; leave queue_id empty for posts predating the workspace |
| ad_spend | One day, platform and campaign in USD |
| email_events | One delivery, open or other event, keyed by event_id |
| signups | One signup, with optional originating session and campaign |
| load_log | One source ingestion per table and timestamp |

`warehouse query` includes the age of every base table read, including tables behind a view. Add `--require-fresh` when automating a report. Selects return up to 200 rows by default and at most 1,000 per call. Long queries are interrupted after five seconds. The database and CSVs remain on the machine. Store client exports in a workspace with access appropriate for that client.

## Connect an agent

Configure a local MCP client to launch the installed command with the workspace's absolute path. Replace the example paths with the installed executable and client directory. A command invoked directly by a desktop client may have a different PATH from your terminal.

```json
{
  "mcpServers": {
    "marketing-warehouse": {
      "command": "/absolute/path/to/venv/bin/mktgkit",
      "args": ["mcp", "--workspace", "/absolute/path/to/client"]
    }
  }
}
```

The client starts a subprocess that exchanges newline-delimited JSON-RPC on standard input and output. Its four tools are `list_tables`, `describe_table`, `query` and `freshness`. Ask the agent to query attribution coverage and return the signup load timestamp with its answer. Keep publication approval outside this read-only connection. The client and its model provider can receive any data returned through tools; choose the data and client accordingly.

The transport is stdio. The server supports the per-request `2026-07-28` protocol and negotiated `2025-11-25`, `2025-06-18`, `2025-03-26` and `2024-11-05` revisions. Older clients receive text results. [MCP versioning and compatibility](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning) · [MCP transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)

The synthetic example can be regenerated with `python tools/make_seed_data.py examples/wrenfield/warehouse/seed` from the repository root.
