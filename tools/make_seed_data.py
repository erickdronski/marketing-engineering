"""Reproduce the fictional Wrenfield CSV exports with the Python standard library."""

import argparse
import csv
import random
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

COLUMNS = {
    "web_sessions": "session_id started_at landing_page source medium campaign_id pageviews",
    "posts": "post_id queue_id channel url published_at impressions clicks",
    "ad_spend": "day platform campaign_id spend_usd impressions clicks",
    "email_events": "event_id sent_at campaign_id event recipient_hash",
    "signups": "signup_id signed_up_at session_id campaign_id plan",
    "load_log": "table_name loaded_at row_count source",
}


def generate(out_dir: Path) -> None:
    rng = random.Random(2611)
    rows = {name: [] for name in COLUMNS}
    sources = ("organic", "ai_answer", "social", "email", "paid", "direct", "referral")
    campaigns = ("route-planning", "dispatch-guides", "trial-onboarding")
    first = date(2026, 10, 1)
    conversions = Counter()
    for day_num in range(50):
        day = (first + timedelta(days=day_num)).isoformat()
        for index in range(30):
            source = rng.choice(sources)
            campaign = rng.choice(campaigns) if source != "direct" else ""
            session = f"session-{30 * day_num + index + 1:04d}"
            stamp = f"{day}T{rng.randrange(24):02}:{rng.randrange(60):02}:00Z"
            rows["web_sessions"].append(
                (session, stamp, "/dispatch-guide", source, "web", campaign, rng.randint(1, 6))
            )
            if rng.random() < 0.08:
                conversions["signups"] += 1
                rows["signups"].append(
                    (
                        "signup-{:03d}".format(conversions["signups"]),
                        stamp,
                        session,
                        campaign if rng.random() < 0.7 else "",
                        "trial",
                    )
                )
        for campaign in campaigns[:2]:
            # Historical synthetic exports, including a paused pilot campaign.
            entry = (
                day,
                "search",
                campaign,
                rng.randrange(120, 300) / 10,
                rng.randrange(400, 800),
                rng.randrange(15, 35),
            )
            # The last historical daily-spend export was loaded on November 18.
            if day < "2026-11-18":
                rows["ad_spend"].append(entry)
        rows["email_events"].append(
            (
                f"event-{day_num:02d}",
                day + "T10:00:00Z",
                "trial-onboarding",
                "delivered",
                f"synthetic-{day_num:02d}",
            )
        )
    rows["posts"] = [
        ("post-01", "", "content", "https://example.org/dispatch", "2026-11-05T09:00:00Z", 465, 21)
    ]
    for name in COLUMNS:
        if name != "load_log":
            loaded = "2026-11-18" if name == "ad_spend" else "2026-11-20"
            rows["load_log"].append((name, loaded + "T06:00:00Z", len(rows[name]), "synthetic CSV"))
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, columns in COLUMNS.items():
        with (out_dir / (name + ".csv")).open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(columns.split())
            writer.writerows(rows[name])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path)
    generate(parser.parse_args().out_dir)
