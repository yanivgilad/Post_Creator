# Article Writer

Local-first AI trend scouting dashboard that runs on your machine, stores daily runs in SQLite, and serves recommendations over a FastAPI website.

## Local workflow

1. Start the web app.
2. Let the background scheduler run daily or trigger a manual run.
3. Review ranked trends and suggested drafts in the browser.

## Commands

```bash
article-writer serve
article-writer run-once
article-writer init-db
```

## Notes

- Product Hunt ingestion is optional and only runs when `ARTICLE_WRITER_PRODUCT_HUNT_TOKEN` is configured.
- The writing layer is template-based for now. A real LLM provider can be added later behind the existing generation interface.
