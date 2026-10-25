from __future__ import annotations

import re
from typing import Any, AsyncGenerator, Dict, List, Optional
from bs4 import BeautifulSoup

from core.search.base import SearchHit
from core.sources.adapters.base import AdapterBrokenError, SourceAdapter
from core.sources.schemas import ProjectPlacement, RawProject, SourceKind


class DevpostAdapter(SourceAdapter):
    """
    Adapter for Devpost hackathon project gallery and winners.
    Selectors are isolated in SELECTORS dictionary.
    """

    name = "devpost"
    domain = "devpost.com"
    source_kind = SourceKind.HACKATHON
    source_family = "hackathons"

    SELECTORS = {
        "title": "#app-title",
        "tagline": "p.large",
        "description": "#app-details-left",
        "authors": "ul#app-team-members .user-profile-link",
        "prizes": ".winner-wrapper, .badge.winner, li:has(.ss-trophy)",
        "links": "#app-details-left a[href^='http']",
        "tags": "#built-with a",
        "gallery_software_card": "a.block-wrapper-link",
    }

    async def discover(
        self,
        limit: int = 50,
        since_year: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        # Enumerates gallery or search URLs
        base = "https://devpost.com/software/search?query=is%3Awinner"
        yield base

    def parse(self, url: str, content: str) -> RawProject:
        soup = BeautifulSoup(content, "html.parser")

        title_el = soup.select_one(self.SELECTORS["title"])
        if not title_el:
            # Fallback to secondary title selector if any
            title_el = soup.select_one("h1")
        if not title_el or not title_el.get_text(strip=True):
            raise AdapterBrokenError(self.name, url, f"Title selector '{self.SELECTORS['title']}' not found.")

        title = title_el.get_text(strip=True)

        tagline_el = soup.select_one(self.SELECTORS["tagline"])
        tagline = tagline_el.get_text(strip=True) if tagline_el else None

        desc_el = soup.select_one(self.SELECTORS["description"])
        if not desc_el:
            desc_el = soup.select_one(".entry-content, article")
        desc = desc_el.get_text("\n", strip=True) if desc_el else ""

        # Extract authors
        author_els = soup.select(self.SELECTORS["authors"])
        authors = [a.get_text(strip=True) for a in author_els if a.get_text(strip=True)]
        team_size = len(authors) if authors else 1

        # Check winner placement
        prizes = [p.get_text(" ", strip=True) for p in soup.select(self.SELECTORS["prizes"])]
        placement = ProjectPlacement.NONE
        prize_name = None
        if prizes:
            placement = ProjectPlacement.WINNER
            prize_name = "; ".join(prizes[:3])

        # Extract tags and tech stack
        tag_els = soup.select(self.SELECTORS["tags"])
        tech_stack = [t.get_text(strip=True) for t in tag_els if t.get_text(strip=True)]

        # Extract links
        links: Dict[str, str] = {}
        for link in soup.select(self.SELECTORS["links"]):
            href = link.get("href", "")
            if "github.com" in href:
                links["repo"] = href
            elif "youtube.com" in href or "youtu.be" in href:
                links["video"] = href
            elif "demo" in href.lower() or "app" in href.lower():
                links["demo"] = href

        # Extract event name from breadcrumb or page if present
        event_name = None
        event_el = soup.select_one("a[href*='devpost.com/hackathons/'], .challenge-title a")
        if event_el:
            event_name = event_el.get_text(strip=True)

        return RawProject(
            source_id=f"devpost:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=title,
            tagline=tagline,
            description_raw=desc,
            authors=authors,
            team_size=team_size,
            event_name=event_name,
            placement=placement,
            prize_name=prize_name,
            links=links,
            tags=tech_stack,
            tech_stack=tech_stack,
            raw_html=content[:4000],
        )

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        # Emits search hit pointing to devpost search
        return [
            SearchHit(
                url=f"https://devpost.com/software/search?query={query}",
                title=f"Devpost Hackathon Projects: {query}",
                snippet=f"Curated winner entries and submissions on Devpost matching {query}",
                source_family=self.source_family,
                provider=self.name,
                rank=1,
                raw_score=0.92,
            )
        ]
