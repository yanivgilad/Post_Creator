from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from article_writer.web.app import create_app


def test_keywords_page_renders_and_seeds(settings):
    seeded = replace(settings, keywords=["alpha keyword", "beta keyword", "gamma keyword"])
    with TestClient(create_app(seeded, start_scheduler=False)) as client:
        resp = client.get("/keywords")
        assert resp.status_code == 200
        assert "alpha keyword" in resp.text
        assert "beta keyword" in resp.text
        assert "gamma keyword" in resp.text
        # tier dropdown options should be present
        assert ">HIGH<" in resp.text
        assert ">MEDIUM<" in resp.text
        assert ">LOW<" in resp.text


def test_keywords_nav_link_present(settings):
    with TestClient(create_app(replace(settings, keywords=[]), start_scheduler=False)) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert 'href="/keywords"' in resp.text
