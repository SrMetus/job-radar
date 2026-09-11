import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from app.main import app


def test_home_serves_html_without_database_or_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("IMPORT_SECRET", "test-secret-must-stay-private")
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "test-secret-must-stay-private" not in response.text
    page = BeautifulSoup(response.text, "html.parser")
    assert page.select_one("h1") is not None
    assert page.select_one('a[href="/docs"]') is not None
    assert page.select_one('select[name="sort"] option').get("value") == "match_score"
    assert page.select_one('select[name="order"] option').get("value") == "desc"
    assert {node.get("name") for node in page.select("input, select")} == {
        "q", "remote", "seniority", "sort", "order",
    }
    expected_options = {
        "remote": [("", "Any work mode"), ("true", "Remote"), ("false", "Not remote")],
        "seniority": [
            ("", "All levels"), ("intern", "Intern"), ("junior", "Junior"),
            ("unknown", "Unknown"), ("senior", "Senior"), ("lead", "Lead"),
            ("staff", "Staff"), ("principal", "Principal"),
        ],
        "sort": [("match_score", "Match score"), ("created_at", "Date added")],
        "order": [("desc", "Descending"), ("asc", "Ascending")],
    }
    for name, expected in expected_options.items():
        assert [
            (option.get("value"), option.get_text())
            for option in page.select(f'select[name="{name}"] > option')
        ] == expected


def test_page_assets_are_served() -> None:
    with TestClient(app) as client:
        page = BeautifulSoup(client.get("/").text, "html.parser")
        paths = [node["src"] for node in page.select("script[src]")]
        paths += [node["href"] for node in page.select('link[rel="stylesheet"]')]
        assert paths
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200
            assert len(response.content) > 0
            assert "html" not in response.headers["content-type"]
        links = client.get("/static/links.json")
        assert links.status_code == 200
        assert links.json() == {
            "github": "https://github.com/SrMetus/job-radar",
            "buy_me_a_coffee": "https://buymeacoffee.com/srmetus",
            "paypal": "https://www.paypal.com/donate/?hosted_button_id=R9T4UHSJ2FFEG",
        }
        assert {
            node["data-public-link"] for node in page.select("[data-public-link]")
        } == set(links.json())
        assert [
            node["data-public-link"] for node in page.select("#support [data-public-link]")
        ] == ["buy_me_a_coffee", "paypal"]
        assert page.select_one('#filters button[type="submit"]') is not None
        for control in ("retry", "load-more"):
            assert page.select_one(f'button#{control}[type="button"]') is not None
        assert client.get("/docs").status_code == 200
        assert client.get("/health").json() == {"status": "ok"}


def test_static_mount_does_not_expose_server_files() -> None:
    with TestClient(app) as client:
        for path in ("/static/.env", "/static/main.py", "/static/%2e%2e/core/config.py"):
            assert client.get(path).status_code == 404


def test_frontend_has_no_kofi_references() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = list((root / "app" / "static").rglob("*")) + list(root.glob("README*"))
    for path in paths:
        if path.is_file():
            assert not re.search(rb"ko[-_ .]?fi", path.read_bytes(), re.IGNORECASE), path


def test_location_display_preserves_source_data() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed to execute the frontend JavaScript regression")
    script = Path(__file__).resolve().parents[1] / "app" / "static" / "app.js"
    # Execute the actual card renderer with a minimal DOM, without starting requests.
    harness = r'''
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(process.argv[1], "utf8");
const context = vm.createContext({
  document: {
    querySelector: () => ({}),
    createElement: () => ({children: [], append(...nodes) { this.children.push(...nodes); }, setAttribute() {}}),
  },
  URLSearchParams, FormData: class {}, URL,
});
vm.runInContext(source.slice(0, source.indexOf('form.addEventListener("submit"')), context);
for (const [input, expected] of JSON.parse(process.argv[2])) {
  const job = Object.freeze({location: input});
  context.job = job;
  const card = vm.runInContext("jobCard(job)", context);
  assert.equal(card.children.find(child => child.className === "location").textContent, expected);
  assert.equal(job.location, input);
}
assert.ok(!source.includes("innerHTML"));
'''
    cases = [
        ("Remote, Remote, Anywhere", "Remote, Anywhere"),
        ("Remote, Remote/Worldwide, Remote/Worldwide, Remote", "Remote, Remote/Worldwide"),
        (" Remote, remote, REMOTE, Santiago, Chile ", "Remote, Santiago, Chile"),
        ("New York, NY, US", "New York, NY, US"),
        ("Remote/Worldwide, Worldwide", "Remote/Worldwide, Worldwide"),
        ("<b>Remote</b>, <b>Remote</b>", "<b>Remote</b>"),
        (None, "Location not listed"),
        (" , , ", "Location not listed"),
    ]
    result = subprocess.run(
        [node, "-e", harness, str(script), json.dumps(cases)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
