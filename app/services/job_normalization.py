"""Small deterministic helpers for imported job content."""

import re

from bs4 import BeautifulSoup

SENIORITY_PATTERNS = (
    ("principal", r"\bprincipal\b"),
    ("staff", r"\bstaff\b"),
    ("lead", r"\b(?:(?:tech|team)\s+)?lead\b"),
    ("senior", r"\b(?:senior|sr)\b"),
    ("junior", r"\b(?:junior|jr|entry[\s-]+level)\b"),
    ("intern", r"\b(?:intern|internship)\b"),
)


def infer_seniority(title: str) -> str:
    for seniority, pattern in SENIORITY_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return seniority
    return "unknown"


def html_to_text(value: str) -> str:
    soup = BeautifulSoup(value, "html.parser")
    for node in soup.select("script, style, img, svg, iframe, noscript, template, [hidden]"):
        node.decompose()
    for node in soup.find_all(["p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "br"]):
        node.insert_before("\n")
        node.insert_after("\n")
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in soup.get_text().splitlines()]
    return "\n".join(line for line in lines if line)


def scoring_content(value: str) -> str:
    text = html_to_text(value)
    text = re.sub(r"(?im)^\s*source\s*:[^\n]*(?:\n|$)", "", text)
    return re.sub(
        r"https?://\S+|www\.\S+|\b[\w.-]+\.(?:org|com|net|io|dev)\b(?:/\S*)?",
        " ", text, flags=re.IGNORECASE,
    )
