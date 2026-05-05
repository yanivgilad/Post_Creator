# Article Writer

Local-first AI trend scouting dashboard that runs on your machine, stores daily runs in SQLite, and serves recommendations over a FastAPI website.

## Local workflow

1. Start the web app.
2. Let the background scheduler run daily or trigger a manual run.
3. Review ranked trends in the browser and create articles on demand.

## Commands

```bash
article-writer serve
article-writer run-once
article-writer init-db
```

## Always-on service

The repo includes a user `systemd` unit at `deploy/systemd/article-writer.service`.

On this machine, the app is installed as a user service and configured to restart automatically:

```bash
systemctl --user status article-writer.service
systemctl --user restart article-writer.service
systemctl --user stop article-writer.service
systemctl --user start article-writer.service
```

Health checks are available at:

```text
http://127.0.0.1:8000/health
```

## Notes

- Product Hunt ingestion is optional and only runs when `ARTICLE_WRITER_PRODUCT_HUNT_TOKEN` is configured.
- Source enable flags, queries, feeds, keywords, and weights now live in `sources.json`. Edit that file and restart the app or user service when you want to change the scouting mix.
- The default RSS mix in `sources.json` includes Microsoft, Apple, and Tesla publication feeds in addition to the existing AI-focused feeds. The RSS source still applies the global keyword filter, so only relevant posts are ranked.
- The writing layer supports `local-template` and direct Gemini calls via `ARTICLE_WRITER_GEMINI_API_KEY`.
- Additional direct providers can be added behind the existing generation interface by routing new `provider/model` names in the article generator.
