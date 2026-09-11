"use strict";

const form = document.querySelector("#filters");
const list = document.querySelector("#job-list");
const status = document.querySelector("#result-status");
const errorMessage = document.querySelector("#error-message");
const emptyMessage = document.querySelector("#empty-message");
const moreButton = document.querySelector("#load-more");
const pageSize = 12;
let filters = new URLSearchParams(new FormData(form));
let offset = 0;
let shown = 0;
let controller;
let retryAppend = false;

function text(value, fallback) {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function displayLocation(value) {
  const seen = new Set();
  return text(value, "Location not listed").split(",").map(part => part.trim())
    .filter(part => {
      const key = part.toLowerCase();
      if (!part || seen.has(key)) return false;
      seen.add(key);
      return true;
    }).join(", ") || "Location not listed";
}

function safeURL(value) {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password
      ? url.href : null;
  } catch {
    return null;
  }
}

function element(tag, className, content) {
  const node = document.createElement(tag);
  node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function externalLink(url, className, label) {
  const link = element("a", className, label);
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function jobCard(job) {
  const card = element("article", "job-card");
  const top = element("div", "card-top");
  const heading = element("div", "card-heading");
  const title = text(job.title, "Untitled opportunity");
  heading.append(element("p", "company", text(job.company, "Company not listed")));
  heading.append(element("h3", "", title));
  const score = element("div", "score");
  const value = typeof job.match_score === "number" && Number.isFinite(job.match_score)
    ? Math.round(Math.max(0, Math.min(100, job.match_score))) : null;
  score.append(element("strong", "", value === null ? "—" : String(value)));
  score.append(element("span", "", value === null ? "NO SCORE" : "/ 100 MATCH"));
  if (value !== null) {
    const meter = document.createElement("meter");
    meter.min = 0;
    meter.max = 100;
    meter.value = value;
    meter.setAttribute("aria-label", `Match score for ${title}`);
    score.append(meter);
  }
  top.append(heading, score);
  card.append(top, element("p", "location", displayLocation(job.location)));
  const bottom = element("div", "card-bottom");
  const tags = element("div", "tags");
  tags.append(element("span", "tag", text(job.seniority, "Unknown seniority")));
  tags.append(element("span", "tag", job.remote === true ? "Remote" : job.remote === false ? "Not remote" : "Work mode unknown"));
  const url = safeURL(job.url);
  const link = url ? externalLink(url, "job-link", "View opportunity ↗")
    : element("span", "link-unavailable", "Link unavailable");
  if (url) link.setAttribute("aria-label", `View ${title} (opens in a new tab)`);
  bottom.append(tags, link);
  card.append(bottom);
  return card;
}

async function loadJobs(append = false) {
  controller?.abort();
  const current = new AbortController();
  controller = current;
  retryAppend = append;
  if (!append) {
    offset = 0;
    shown = 0;
    list.replaceChildren();
  }
  moreButton.hidden = true;
  errorMessage.hidden = true;
  emptyMessage.hidden = true;
  list.setAttribute("aria-busy", "true");
  status.textContent = append ? "Loading more opportunities…" : "Loading opportunities…";
  const params = new URLSearchParams(filters);
  for (const [key, value] of [...params]) if (!value) params.delete(key);
  params.set("limit", String(pageSize));
  params.set("offset", String(offset));
  // Bound slow requests, allowing a visible error and manual retry.
  const timeout = setTimeout(() => current.abort(), 20000);
  try {
    const response = await fetch(`/jobs?${params}`, {signal: current.signal});
    if (!response.ok) throw new Error("Jobs unavailable");
    const jobs = await response.json();
    if (!Array.isArray(jobs)) throw new Error("Invalid response");
    if (controller !== current) return;
    const fragment = document.createDocumentFragment();
    const cards = jobs.filter(job => job && typeof job === "object" && !Array.isArray(job)).map(jobCard);
    fragment.append(...cards);
    list.append(fragment);
    offset += jobs.length;
    shown += cards.length;
    status.textContent = shown ? `${shown} ${shown === 1 ? "opportunity" : "opportunities"} shown` : "No matching opportunities";
    emptyMessage.hidden = shown > 0;
    moreButton.hidden = jobs.length < pageSize;
    if (append && cards.length) {
      cards[0].tabIndex = -1;
      cards[0].focus({preventScroll: true});
    }
  } catch {
    if (controller !== current) return;
    errorMessage.hidden = false;
    status.textContent = shown ? `${shown} opportunities shown · Could not load more` : "Opportunities unavailable";
  } finally {
    clearTimeout(timeout);
    if (controller === current) list.setAttribute("aria-busy", "false");
  }
}

form.addEventListener("submit", event => {
  event.preventDefault();
  filters = new URLSearchParams(new FormData(form));
  filters.set("q", filters.get("q").trim());
  loadJobs();
});
moreButton.addEventListener("click", () => loadJobs(true));
document.querySelector("#retry").addEventListener("click", () => loadJobs(retryAppend));

async function configurePublicLinks() {
  try {
    const response = await fetch("/static/links.json");
    if (!response.ok) return;
    const links = await response.json();
    if (!links || typeof links !== "object" || Array.isArray(links)) return;
    for (const placeholder of document.querySelectorAll("[data-public-link]")) {
      const key = placeholder.dataset.publicLink;
      const url = safeURL(links[key]);
      if (!url) continue;
      const label = key === "github" ? "GitHub ↗" : placeholder.firstChild.textContent.trim();
      const link = externalLink(url, key === "github" ? "" : "support-option", label);
      link.setAttribute("aria-label", `${label} (opens in a new tab)`);
      placeholder.replaceWith(link);
    }
    if (["buy_me_a_coffee", "paypal"].some(key => safeURL(links[key]))) {
      document.querySelector("#support h2 + p").textContent = "Like what’s being built? Choose a way to support the project.";
    }
  } catch {
    // Optional public links must never prevent the job browser from working.
  }
}

configurePublicLinks();
loadJobs();
