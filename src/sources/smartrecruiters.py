"""SmartRecruiters ATS board source adapter."""
from __future__ import annotations

from html import unescape
import logging
import os
import re
from urllib.parse import urlparse

from ..classifier import classify
from ..utils.http import get_session
from .base import BaseSource, Job, looks_like_metadata_only_description, make_location, merge_text

log = logging.getLogger(__name__)

_API_BASE = "https://api.smartrecruiters.com/v1/companies"
_DETAIL_BUDGET_PER_BOARD = 12
_DETAIL_TITLE_MARKERS = (
    "data",
    "analytics",
    "analyst",
    "scientist",
    "machine learning",
    "ml ",
    " ai",
    "business intelligence",
    "bi ",
    "insights",
    "reporting",
    "forecast",
    "experiment",
    "mlops",
    "platform",
)


def _company_slug(board_url: str) -> str:
    parts = [p for p in (urlparse(board_url or "").path or "").split("/") if p]
    return parts[0].strip() if parts else ""


def _board_id(board_url: str) -> str:
    slug = _company_slug(board_url).lower()
    return f"smartrecruiters:{slug}" if slug else "smartrecruiters:"


def _extract_description(detail: dict) -> str:
    if not isinstance(detail, dict):
        return ""
    job_ad = detail.get("jobAd")
    sections = (job_ad.get("sections") if isinstance(job_ad, dict) else None) or detail.get("sections") or []
    if isinstance(sections, dict):
        section_titles = {
            "companyDescription": "Company Description",
            "jobDescription": "Job Description",
            "qualifications": "Qualifications",
            "additionalInformation": "Additional Information",
        }
        normalized_sections = []
        for key, section in sections.items():
            title = section_titles.get(key, re.sub(r"([a-z])([A-Z])", r"\1 \2", key))
            if isinstance(section, str):
                section = {"text": section}
            if isinstance(section, dict):
                normalized_sections.append({
                    **section,
                    "title": section.get("title") or section.get("name") or title,
                })
        sections = normalized_sections
    parts: list[str] = []
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = str(section.get("title") or section.get("name") or "").strip()
            text = str(section.get("text") or section.get("content") or "").strip()
            if text:
                cleaned = re.sub(r"<[^>]+>", " ", text)
                cleaned = re.sub(r"\s+", " ", unescape(cleaned)).strip()
                parts.append(f"{title}: {cleaned}" if title else cleaned)
    structured = merge_text(
        parts,
        detail.get("description"),
        detail.get("jobDescription"),
        detail.get("descriptionTeaser"),
        detail.get("summary"),
        detail.get("responsibilities"),
        detail.get("qualifications"),
        detail.get("skills"),
    )
    structured = structured.strip()
    if looks_like_metadata_only_description(structured):
        return ""
    return structured


def _should_fetch_detail(title: str, *, label: str, budget_remaining: int) -> bool:
    if label in {"yes", "maybe"}:
        return True
    if budget_remaining <= 0:
        return False
    normalized = f" {str(title or '').strip().lower()} "
    return any(marker in normalized for marker in _DETAIL_TITLE_MARKERS)


class SmartRecruitersSource(BaseSource):
    """Fetches jobs from a single SmartRecruiters board."""

    def __init__(self, company: str, board_url: str, *, max_jobs: int | None = None) -> None:
        slug = _company_slug(board_url)
        self.name = f"smartrecruiters:{slug}"
        self.company = company
        self.board_url = board_url
        self._slug = slug
        self.board_id = _board_id(board_url)
        self.max_jobs = max(1, int(max_jobs if max_jobs is not None else os.environ.get("SMARTRECRUITERS_MAX_JOBS", "5000")))

    def fetch(self, seen_keys: set[str], timeout: int = 30) -> list[Job]:
        if not self._slug:
            return []

        sess = get_session("smartrecruiters")
        headers = {"accept": "application/json", "user-agent": "Mozilla/5.0"}

        all_raw: list[dict] = []
        offset = 0
        limit = 100
        seen_ids: set[str] = set()
        total = None

        while True:
            url = f"{_API_BASE}/{self._slug}/postings"
            r = sess.get(url, params={"offset": offset, "limit": limit}, headers=headers, timeout=timeout)
            r.raise_for_status()

            data = r.json() if r.content else {}
            posts = data.get("content", data.get("postings")) if isinstance(data, dict) else None
            if not isinstance(posts, list):
                raise ValueError(f"Unexpected SmartRecruiters listing schema for {self._slug}")
            if not posts:
                break

            fresh = []
            for post in posts:
                ident = str(post.get("id") or post.get("ref") or "")
                if not ident or ident not in seen_ids:
                    fresh.append(post)
                    if ident:
                        seen_ids.add(ident)
            if not fresh:
                log.warning("smartrecruiters:%s: repeated page at offset %s; stopping pagination", self._slug, offset)
                break
            all_raw.extend(fresh[: self.max_jobs - len(all_raw)])
            offset += len(posts)
            raw_total = data.get("totalFound")
            total = int(raw_total) if str(raw_total).isdigit() else None
            if len(all_raw) >= self.max_jobs and (total is None or total > len(all_raw)):
                log.warning("smartrecruiters:%s: truncated at %s jobs (API total=%s); raise SMARTRECRUITERS_MAX_JOBS to expand coverage", self._slug, self.max_jobs, total)
                break
            if total is not None and offset >= total:
                break

        result: list[Job] = []
        detail_budget_remaining = _DETAIL_BUDGET_PER_BOARD
        for raw in all_raw:
            pid = str(raw.get("id") or raw.get("ref") or "")
            key = (
                f"smartrecruiters:{self._slug}:{pid}" if pid
                else f"smartrecruiters:{self._slug}:url:{raw.get('referrer','')}"
            )
            title = raw.get("name") or raw.get("jobTitle") or "Unknown Title"
            loc_obj = raw.get("location") or {}
            if isinstance(loc_obj, dict):
                loc = make_location([loc_obj.get("city"), loc_obj.get("region") or loc_obj.get("state"), loc_obj.get("country")])
            else:
                loc = str(loc_obj) if loc_obj else "Unknown Location"
            posted = raw.get("releasedDate") or raw.get("publicationDate") or raw.get("createdOn") or ""
            url_job = raw.get("referrer") or raw.get("applyUrl") or raw.get("url") or self.board_url
            description = ""
            cr = classify(title)
            fetch_detail = bool(pid) and _should_fetch_detail(title, label=cr.label, budget_remaining=detail_budget_remaining)
            if fetch_detail:
                try:
                    detail_url = f"{_API_BASE}/{self._slug}/postings/{pid}"
                    detail_resp = sess.get(detail_url, headers=headers, timeout=timeout)
                    detail_resp.raise_for_status()
                    description = _extract_description(detail_resp.json() if detail_resp.content else {})
                    if cr.label not in {"yes", "maybe"}:
                        detail_budget_remaining -= 1
                except Exception as exc:
                    log.debug("smartrecruiters:%s detail fetch failed for %s: %s", self._slug, pid, exc)
            result.append(Job(
                key=key, source="smartrecruiters", company=self.company,
                title=title, location=loc, url=url_job,
                posted=posted, description=description, score=cr.score, label=cr.label,
            ))

        log.debug("smartrecruiters:%s: fetched %d jobs", self._slug, len(result))
        return result
