CREATE TABLE web_sessions (
  session_id TEXT PRIMARY KEY NOT NULL, started_at TEXT NOT NULL,
  landing_page TEXT NOT NULL, source TEXT, medium TEXT, campaign_id TEXT,
  pageviews INTEGER NOT NULL CHECK (typeof(pageviews) = 'integer' AND pageviews >= 0)
);
CREATE TABLE posts (
  post_id TEXT PRIMARY KEY NOT NULL, queue_id TEXT, channel TEXT NOT NULL, url TEXT,
  published_at TEXT NOT NULL,
  impressions INTEGER NOT NULL CHECK (typeof(impressions) = 'integer' AND impressions >= 0),
  clicks INTEGER NOT NULL CHECK (typeof(clicks) = 'integer' AND clicks >= 0)
);
CREATE TABLE ad_spend (
  day TEXT NOT NULL, platform TEXT NOT NULL, campaign_id TEXT NOT NULL,
  spend_usd REAL NOT NULL CHECK (typeof(spend_usd) IN ('real','integer') AND spend_usd >= 0 AND spend_usd < 1e308),
  impressions INTEGER NOT NULL CHECK (typeof(impressions) = 'integer' AND impressions >= 0),
  clicks INTEGER NOT NULL CHECK (typeof(clicks) = 'integer' AND clicks >= 0),
  PRIMARY KEY (day, platform, campaign_id)
);
CREATE TABLE email_events (
  event_id TEXT PRIMARY KEY NOT NULL, sent_at TEXT NOT NULL, campaign_id TEXT,
  event TEXT NOT NULL, recipient_hash TEXT
);
CREATE TABLE signups (
  signup_id TEXT PRIMARY KEY NOT NULL, signed_up_at TEXT NOT NULL, session_id TEXT,
  campaign_id TEXT, plan TEXT
);
CREATE TABLE load_log (
  table_name TEXT NOT NULL CHECK (table_name IN ('web_sessions','posts','ad_spend','email_events','signups')),
  loaded_at TEXT NOT NULL, row_count INTEGER NOT NULL CHECK (typeof(row_count) = 'integer' AND row_count >= 0),
  source TEXT NOT NULL, PRIMARY KEY (table_name, loaded_at)
);
