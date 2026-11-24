-- Sum each source at campaign grain before combining them.
CREATE VIEW campaign_performance AS
WITH spend AS (
  SELECT campaign_id, SUM(spend_usd) AS spend_usd FROM ad_spend GROUP BY campaign_id
), visits AS (
  SELECT campaign_id, COUNT(*) AS sessions FROM web_sessions
  WHERE campaign_id IS NOT NULL GROUP BY campaign_id
), leads AS (
  SELECT campaign_id, COUNT(*) AS signups FROM signups
  WHERE campaign_id IS NOT NULL GROUP BY campaign_id
), campaigns AS (
  SELECT campaign_id FROM spend UNION SELECT campaign_id FROM visits UNION SELECT campaign_id FROM leads
)
SELECT c.campaign_id, ROUND(s.spend_usd, 2) AS spend_usd, COALESCE(v.sessions, 0) AS sessions,
       COALESCE(l.signups, 0) AS signups,
       ROUND(s.spend_usd / NULLIF(l.signups, 0), 2) AS cost_per_signup
FROM campaigns c LEFT JOIN spend s USING (campaign_id)
LEFT JOIN visits v USING (campaign_id) LEFT JOIN leads l USING (campaign_id);

CREATE VIEW attribution_coverage AS
SELECT COUNT(*) AS signups, COUNT(campaign_id) AS with_campaign_id,
       ROUND(1.0 * COUNT(campaign_id) / NULLIF(COUNT(*), 0), 4) AS share_with_campaign_id
FROM signups;
