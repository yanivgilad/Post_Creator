from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import logging

from article_writer.models import utc_now
from article_writer.sources.rss import RSSSource


def test_rss_fetch_skips_failed_feeds_and_keeps_other_items(settings, monkeypatch, caplog):
    source = RSSSource()
    current_settings = replace(
        settings,
        enable_rss=True,
        rss_feeds=["https://bad.example/feed.xml", "https://good.example/feed.xml"],
    )
    published_at = utc_now().strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml_text = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<rss version=\"2.0\">
  <channel>
    <item>
      <title>Copilot agents for robotics</title>
      <link>https://example.com/copilot-robotics</link>
      <description>Autonomous robotics update.</description>
      <pubDate>{published_at}</pubDate>
    </item>
  </channel>
</rss>
"""

    def fake_get_text(url, current_settings, headers=None):
        if url == "https://bad.example/feed.xml":
            raise RuntimeError("rss request failed with status 404")
        return xml_text

    monkeypatch.setattr(source, "_get_text", fake_get_text)

    with caplog.at_level(logging.INFO):
        items = source.fetch(utc_now() - timedelta(days=1), current_settings)

    assert len(items) == 1
    assert items[0].metadata["feed_url"] == "https://good.example/feed.xml"
    assert any("feed failed https://bad.example/feed.xml" in record.message for record in caplog.records)
    assert any("feed https://good.example/feed.xml fetched 1 items" in record.message for record in caplog.records)