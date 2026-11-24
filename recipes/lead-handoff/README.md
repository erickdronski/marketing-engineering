# Reconcile quote requests to booked estimates

A service business gets quote requests on its website and records bookings in a separate dispatch system. Before automating follow-up, the dispatcher needs to know which requests already booked and which records need attention. This recipe joins two de-identified CSV exports using the form’s request ID. Python 3.9+ runs it locally with no dependencies.

From the repository root, run the fictional example.

```sh
python3 recipes/lead-handoff/reconcile.py \
  --requests recipes/lead-handoff/example/requests.csv \
  --bookings recipes/lead-handoff/example/bookings.csv \
  --start 2026-11-02 --end 2026-11-08 --as-of 2026-11-16 \
  --out out/lead-handoff-demo
```

The example produces **2 booked estimates from 3 eligible requests**. The tagged page has 1 booking from 2 requests. The third request booked with an unknown source. One duplicate form delivery and one employee test account for the other two form rows. A reschedule leaves two booking records for R1, which counts once.

## Prepare two exports

Bring the request ID from the form into the dispatch record. If the systems lack a shared ID, add a field or have the operator record it during the pilot. Use a client-approved reporting time zone for both exports. Supply local calendar dates as `YYYY-MM-DD`. Export the full set of requests referred to by the bookings, even if some fall outside the cohort.

| File | Required columns | Meaning |
|---|---|---|
| Requests | `request_id,request_date,source,is_test` | One logical form submission, its creation date, a short campaign or page code, and `true` or `false` for employee tests. A blank source or the literal `unknown` stays unattributed. |
| Bookings | `booking_id,request_id,booked_date` | One booking event, its form request ID and the day the estimate was booked. A reschedule can have a different booking ID. Export creation events for booked estimates. |

Use UTF-8 CSV with headers. The recipe accepts the columns in any order. IDs and source codes are case-sensitive, start with a letter or digit, and allow letters, digits, periods, underscores, colons and hyphens. Keep names, email addresses, phone numbers, full URLs and CRM notes out of the exports. Extra columns are rejected. Keep inputs and outputs in the client’s approved storage.

The cohort includes requests received from `--start` through `--end`, inclusive. By default, a booking counts from the request date through seven calendar days later, inclusive. Use `--window-days` to change the agreement. A late booking can be real even though it falls outside this metric. Rows dated after the as-of day do not count as bookings. The report is final once the last cohort day has had its full window and the inputs reconcile. The operator confirms both exports are complete through the declared as-of day. This measure counts a booking when it was made. Completed jobs, cancellations and revenue require separate outcome events.

## Hand the result to the dispatcher

| Output | What the operator does |
|---|---|
| `summary.json` | Compare the numerator and denominator to dispatch, then review `by_source` and `tagged_mature_requests`. The booking rate is empty for an unfinished, disputed or empty denominator. |
| `worklist.csv` | Check matured requests against dispatch. A request with unknown source gets a separate attribution task, so the worklist can have more rows than requests. The operator confirms eligibility and contact preferences in the client system before considering any follow-up. |
| `exceptions.csv` | Resolve missing keys, booking IDs with conflicting details, unmatched references or booking dates before request creation. The file identifies the source export and the record, or a line number when its own ID is missing. |

Identical rows for the same ID are collapsed. Conflicting versions of one request or booking are excluded and listed for review. If the source system legitimately changes a record, export one canonical version or add an explicit event history before using it here. A booking with no matching request never gets matched by guessing. Counts from a run with exceptions describe the remaining reconciled rows and are held for review.

A ready report exits 0. A provisional run or one with data exceptions writes all three outputs and exits 1. An invalid file, argument or destination exits 2. Rerunning identical inputs and dates reuses identical output. If the result changes, choose a new output directory so the prior run remains available.

For a recurring client job, have the client schedule the same command after both exports finish, using a fresh dated output path. Route exit 1 to the operator and exit 2 to the integration owner. A CRM or messaging adapter would be a separate client implementation. The recipe has no credentials, network connection or ability to send messages. [Consulting workflow](../../docs/consulting/README.md)
