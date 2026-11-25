# Choose a channel experiment

Start with a decision the client can make at the end of a pilot. A dispatcher deciding which service to promote needs booked estimates. A software team deciding which demo to fund needs qualified opportunities. Pick one of those outcomes, confirm that someone records it, and choose a channel where you can follow a customer through to that record.

| Where the client is stuck | First experiment | What the consultant hands over |
|---|---|---|
| Creator videos get attention, but the team cannot tell which ones bring inquiries | Test two original demonstrations of the same customer problem. | A creator brief, usage-rights record and outcome by asset. [Creator content](creative-and-social.md#creator-content-people-can-recognize) |
| A paid campaign brings cheap signups that rarely become customers | Trace a test conversion, then compare two creative concepts against a downstream event. | An event check and a capped test with a cost per qualified outcome. [Meta ads](creative-and-social.md#meta-ads-with-a-traceable-outcome) |
| Sales credits LinkedIn for deals that buyers rarely click through to | Pilot one useful guide with an identifiable audience and record how accounts enter the pipeline. | An account report showing traced clicks, account-level ad exposure and overlap. [LinkedIn](creative-and-social.md#linkedin-guides-that-reach-buyers) |
| A sales team sends generic introductions | Use a dated business signal to prepare a relevant question and a short demo for a rep. | An account brief, synthetic demo and record of the prospect’s next step. [Outbound](outbound.md) |
| Search traffic has fallen or several pages compete for the same job | Inspect comparable periods and the intent behind each page before changing it. | A page-level decision log and a follow-up measurement. [Organic search](search-and-ai.md#choose-a-search-change) |
| Buyers use AI to research a shortlist, but the team only has anecdotes | Repeat a small set of real buyer questions and inspect the sources cited in each answer. | A dated observation log and one evidence-backed page improvement. [AI search](search-and-ai.md#check-what-an-assistant-actually-shows) |

[Copy the pilot worksheet](pilot-worksheet.md) into the client’s private workspace. It includes a worked example where the asset with fewer clicks produces more booked estimates. For the engagement fee, access and ongoing support agreement, use the [engagement brief](../engagement-brief.md).

## Rehearse the budget decision

The fictional Wrenfield workspace already contains campaign, signup and spend exports. From the root of a clone, create a fresh practice directory and inspect one campaign.

```sh
python3 -m mktgkit init channel-practice --example
python3 -m mktgkit warehouse build -w channel-practice
python3 -m mktgkit warehouse query "SELECT campaign_id, spend_usd, signups, cost_per_signup FROM campaign_performance WHERE campaign_id = 'route-planning'" -w channel-practice
python3 -m mktgkit warehouse query "SELECT * FROM attribution_coverage" -w channel-practice
python3 -m mktgkit warehouse query "SELECT * FROM campaign_performance WHERE campaign_id = 'route-planning'" --require-fresh -w channel-practice
```

The first query reports $1,001.20 in recorded media spend and 18 tagged signups, or $55.62 per tagged signup. The second shows that only 76 of 125 signups across the example carry a campaign ID. Leave the other 49 unattributed. The final command deliberately exits with code 5 because the spend export is 57 hours old at the example clock. The analyst can hand over those findings now. The budget owner needs refreshed spend and the downstream customer records before deciding whether buying another signup makes sense. [Warehouse definitions](../../warehouse.md)

For a client pilot, assign a source to each number. Use the ad platform for spend, the form for requests, dispatch or CRM for bookings, and billing for paid jobs. Carry the campaign ID to the form and the request ID into dispatch. Use a job or invoice ID for revenue, check when each export last loaded, and send unmatched records to the named operator. The [lead-handoff recipe](../../../recipes/lead-handoff/README.md) rehearses the form-to-dispatch portion with two CSVs.

## Source and scope

Ira Bodnar’s Ryze AI carousel prompted these six channel choices. The worksheet, client scenarios and decision rules here are original applications for small teams. The post’s company results, proposed rates and platform observations are hypotheses to test. A client supplies its own economics and evidence. The existing CLI checks local approvals and queries exports. A live ad buy, send, CRM write or checkout needs a client-owned system and operator. [Original post](https://x.com/irabukht/status/2125559851564872014) · [Action permissions](../../permissions.md) · [Adapter contract](../../automation.md)
