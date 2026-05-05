from __future__ import annotations

from article_writer.config import Settings
from article_writer.models import DraftArtifact, RankedTrend


class TemplateDraftGenerator:
    def generate(self, trends: list[RankedTrend], settings: Settings) -> list[DraftArtifact]:
        if not trends:
            empty = [
                DraftArtifact(
                    platform="digest",
                    title="No trends captured yet",
                    body="No new AI items matched the configured sources and keyword filters during the last run.",
                )
            ]
            if settings.draft_count > 0:
                empty.extend(
                    DraftArtifact(
                        platform=platform,
                        title=f"No new {platform} draft",
                        body="No fresh trends were available for a useful draft.",
                        metadata={"empty": True},
                    )
                    for platform in ["x", "linkedin", "reddit"][: settings.draft_count]
                )
            return empty

        top_titles = [trend.source_item.title for trend in trends[:3]]
        digest_lines = ["Top AI trends from the latest run:"]
        for index, trend in enumerate(trends, start=1):
            digest_lines.append(
                f"{index}. {trend.source_item.title} ({trend.source_item.source_name}) - {trend.reason_summary}."
            )

        x_lines = [
            "Fresh AI updates worth talking about today:",
            *[f"- {title}" for title in top_titles],
            "Which one is most useful in practice?",
        ]
        linkedin_lines = [
            "Three AI developments stood out in the last 72 hours.",
            *[f"- {trend.source_item.title}: {trend.reason_summary}." for trend in trends[:3]],
            "I would use these to start a short commentary post with one concrete take per item.",
        ]
        reddit_lines = [
            "Discussion prompt: which of these recent AI launches or write-ups actually matters?",
            *[f"- {trend.source_item.title}" for trend in trends[:5]],
        ]

        drafts = [
            DraftArtifact(
                platform="digest",
                title="Daily AI trend digest",
                body="\n".join(digest_lines),
                metadata={"trend_count": len(trends)},
            )
        ]

        if settings.draft_count >= 1:
            drafts.append(
                DraftArtifact(
                    platform="x",
                    title="X post draft",
                    body="\n".join(x_lines),
                    metadata={"style": "short-form"},
                )
            )
        if settings.draft_count >= 2:
            drafts.append(
                DraftArtifact(
                    platform="linkedin",
                    title="LinkedIn draft",
                    body="\n".join(linkedin_lines),
                    metadata={"style": "professional"},
                )
            )
        if settings.draft_count >= 3:
            drafts.append(
                DraftArtifact(
                    platform="reddit",
                    title="Reddit discussion draft",
                    body="\n".join(reddit_lines),
                    metadata={"style": "discussion"},
                )
            )
        return drafts
