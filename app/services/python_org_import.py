"""Import one public Python.org jobs listing page; never follow detail links."""

import re
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.schemas.job import JobCreate, JobImportSummary
from app.services.job_import import ExternalJobSourceError, persist_new_jobs
from app.services.job_normalization import infer_seniority


def normalize_python_org_job(card: Tag, source_url: str) -> JobCreate | None:
    company_node = card.select_one(".listing-company-name")
    location_node = card.select_one(".listing-location")
    link = company_node.select_one("a[href]") if company_node else None
    if company_node is None or location_node is None or link is None:
        return None
    href = link.get("href")
    if not isinstance(href, str) or not href.strip():
        return None
    url = urljoin(source_url, href.strip())
    try:
        TypeAdapter(HttpUrl).validate_python(url)
    except ValidationError:
        return None
    parsed = urlsplit(url)
    if parsed.hostname != "www.python.org" or not re.fullmatch(r"/jobs/\d+/", parsed.path):
        return None
    if parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        return None
    title = link.get_text(" ", strip=True)
    # Remove the title and optional New badge, leaving the company text.
    company_copy = BeautifulSoup(str(company_node), "html.parser")
    for node in company_copy.select("a, .listing-new"):
        node.decompose()
    company = company_copy.get_text(" ", strip=True)
    location = location_node.get_text(" ", strip=True)
    if any(not value or "\x00" in value for value in (title, company, location)):
        return None
    categories = [
        node.get_text(" ", strip=True)
        for node in card.select(".listing-job-type, .listing-company-category")
    ]
    description = "; ".join(value for value in categories if value)
    work_mode = f"{title} {location}"
    remote = bool(re.search(r"\bremote\b", work_mode, re.IGNORECASE))
    if re.search(r"\b(?:not|no|non)[\s-]+remote\b", work_mode, re.IGNORECASE):
        remote = False
    return JobCreate(
        title=title, company=company, location=location, url=url,
        remote=remote, seniority=infer_seniority(title), description=description,
    )


def parse_python_org_jobs(html: str, source_url: str) -> tuple[int, list[JobCreate]]:
    soup = BeautifulSoup(html, "html.parser")
    listing = soup.select_one(".list-recent-jobs")
    if listing is None:
        raise ExternalJobSourceError("Python.org jobs listing was not found; page structure may have changed.")
    cards = listing.find_all("li", recursive=False)
    jobs = [job for card in cards if (job := normalize_python_org_job(card, source_url)) is not None]
    return len(cards), jobs


def import_python_org_jobs(session: Session, source_url: str) -> JobImportSummary:
    try:
        response = httpx.get(source_url, timeout=15.0, follow_redirects=False,
                             headers={"User-Agent": "JobRadar/0.1 (job listing importer)"})
        response.raise_for_status()
    except httpx.HTTPError:
        raise ExternalJobSourceError("Python.org job source request failed.") from None
    if "text/html" not in response.headers.get("content-type", "").lower():
        raise ExternalJobSourceError("Python.org job source did not return HTML.")
    fetched, jobs = parse_python_org_jobs(response.text, source_url)
    return persist_new_jobs(session, jobs, fetched=fetched)
