# Deliver a marketing engineering engagement

Marketing engineering turns a business question into a workflow someone can run, measure and repair. For a business with one marketer, that might mean knowing which service page led to a booked estimate. For a team with several channels, it might mean finding out why campaign signups never reach the right salesperson.

Start with a decision the owner makes regularly. Ask them to show you the last time they made it. Follow one real example from the first customer touch to the recorded outcome. The gap you can actually observe makes a better first engagement than a list of tools to install.

## Choose the first job

These are fictional engagement designs. The systems, numbers and acceptance criteria are examples you can change with a client.

| | Local home-services firm | Midsize B2B software company |
|---|---|---|
| Decision | Which service page should the owner improve next? | Which campaigns bring signups that sales accepts? |
| Trace one record | Service page → quote form → dispatch record → booked estimate | Campaign link → signup → CRM contact → sales acceptance |
| First useful build | Add a stable campaign code to one service page, preserve it on the quote request, and match requests to estimates by request ID. Start with a weekly export. | Agree on campaign codes and a signup ID. Join the signup export to a CRM status history. Give sales operations a list of unmatched records before adding automated routing. |
| Operating owner | Dispatcher records the booking. Owner reviews the report and approves the next page edit. | Marketing operations owns the campaign mapping. Sales operations owns the acceptance event and investigates rejected records. |
| Pilot boundary | One service, one page, one form. Phone bookings need their own intake path. | One campaign family and one sales team. Use the same sales acceptance window for each campaign. |

If the form cannot carry an ID into the dispatch system, test whether the dispatcher can record it manually for a pilot. If the CRM only stores the current lead status, begin collecting dated acceptance events. Both are meaningful findings the client can act on before buying a connector.

Once that handoff works, choose a channel where the result can change an operating decision. The [channel experiment field guide](channel-experiments/README.md) pairs six options with a copyable worksheet, a fictional budget decision and an offline data-quality check.

## Run the engagement

1. **Discovery.** Sit with the person doing the work. Trace a success, a duplicate and an exception using redacted records. Record where each ID is created, which clock records each event, who can correct mistakes, and what decision is currently delayed.
2. **Scope and price.** Agree on one workflow, a pilot owner, the allowed data, a fixed set of deliverables and an acceptance exercise. Separate the one-time build from recurring review, software and support costs. Record who pays for connectors and what would require a new estimate. [Engagement brief](engagement-brief.md)
3. **Build the smallest complete loop.** Create a private workspace for the client. Write down the goal, source and claim owner. Have an agent draft one asset, a reviewer check it, and a named operator carry out the approved action in the client’s system. Capture its reference and the downstream outcome. The included toolkit runs offline. Live connectors and their credentials belong in the client’s environment.
4. **Rehearse exceptions.** Submit an unsupported performance figure, change approved copy, resupply an event that was already processed and withhold a required source. Record which checks the toolkit performs and which the client’s integration or operator must perform. A failed delivery needs a named owner and a recoverable record.
5. **Hand over and observe.** Someone from the client team runs the exercise from a clean copy with the consultant watching. Have them pause the workflow, correct a record, and produce the next report. Name a backup owner and agree when the client can operate without recurring consultant support. [Handoff checklist](handoff.md)

## Define a metric that reconciles to the source

For the home-services pilot, use **booked estimates per eligible quote request**. Count distinct request IDs created during the reporting week in the client’s chosen time zone. Exclude employee tests and deduplicate repeat deliveries of the same ID. Count a request in the numerator once if dispatch records a booked estimate within seven days of that request. The seven-day rule is an example the owner must approve. Keep recent weeks provisional until their window closes.

Consider this deliberately small batch after its booking window has closed.

| Request ID | Source | What happened |
|---|---|---|
| R1 | service-page | Booked twice after a reschedule |
| R2 | service-page | Remained open |
| R2 | service-page | The same form event was delivered twice |
| R3 | unknown | Booked once |
| R4 | service-page | An employee tested the form |

The expected sitewide result is **2 booked / 3 eligible requests**. For the tagged page it is **1 / 2**. Source coverage is **2 / 3**. Assigning R3 to the service page would conceal the attribution gap. Report an empty denominator as “no eligible requests.” A booking associated with a page establishes a traceable relationship. Estimating the extra bookings caused by a page change requires a separate comparison.

Run the same example against the supplied CSV exports to produce an operator worklist and an exceptions file. [Lead handoff recipe](../../recipes/lead-handoff/README.md)

For the B2B pilot, replace the booking event with a dated sales acceptance. Preserve multiple status changes in the source and count the first qualifying acceptance per signup. Agree on how returning customers, duplicate contacts and unmatched IDs are treated before comparing campaigns.

## Give each agent a bounded job

| Participant | Input | Output another person can inspect |
|---|---|---|
| Research agent | Approved product facts and a dated data export | A source reference, date and known gaps for each proposed claim |
| Drafting agent | One audience, one offer and the supported claims | One asset, its intended channel and the claims it cites |
| Reviewer | Draft, source and client policy | Approval of that exact version, or an edit request such as “Replace the savings figure in the opening with the verified booking count.” |
| Operator | Approved copy and destination | Publication or delivery reference, owner and time |
| Measurement owner | Source export and outcome records | Numerator, denominator, coverage, freshness and exceptions |

Start with the operator performing the external action. To automate it later, require the adapter to check the exact approved content, use a stable delivery key, record the provider’s receipt and reconcile an uncertain send before retrying. Keep reviewer and spending decisions with the named client owner. A source refresh failure should suspend decisions that require that source. A missing connection or a silent duplicate is a reason to fix the workflow before extending it to more channels.
