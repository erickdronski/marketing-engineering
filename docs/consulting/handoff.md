# Operator handoff

Complete this in the client’s private workspace. Record account owners and credential locations in the client’s secret manager. Keep the credential values there.

| Operating detail | Client record |
|---|---|
| Workflow, release or commit, last verified date | [ ] |
| Primary operator, backup and reviewer | [Names, contact route and absence coverage] |
| Inputs | [Source, expected fields, owning team, delivery method, time zone and normal arrival time] |
| Run and inspect | [Exact commands or dashboard path, working directory and where output appears] |
| External actions | [Manual step or connector, destination, required approval and delivery receipt location] |
| Measure and reconcile | [Metric definition, original records to compare, coverage check and reporting schedule] |
| Alert and pause | [Failure signal, who receives it, where to hold deliveries and who can resume] |
| Access and upkeep | [Account owner, credential rotation/revocation, retention, update owner and support end date] |

## Rehearse with the incoming operator

- [ ] Start with the documented release in a fresh test workspace. Trace a sample from source through review to its result. Record the input, output and IDs.
- [ ] Change approved copy. Show how the operator detects the change and obtains fresh approval.
- [ ] Delay a source refresh and show what gets held. Confirm the previous report still displays its original measurement date.
- [ ] If there is a live integration, use its test destination. Interrupt a delivery after dispatch but before recording its receipt. Demonstrate how the operator checks the destination or provider receipt by delivery key before retrying. If the outcome cannot be determined, assign the item for manual reconciliation.
- [ ] Pause the schedule or stop manual deliveries. Restore the last known-good settings and rerun against test data. Explain which previously published items would need a separate correction.
- [ ] Ask the backup owner to produce the agreed report and reconcile one outcome to its source. Record their sign-off.

| Open item | Operational consequence | Owner | Due date | Closure evidence |
|---|---|---|---|---|
| [ ] | [ ] | [ ] | [ ] | [ ] |

Handoff accepted by [operator] and [business owner] on [date]. Next review [date or triggering event].
