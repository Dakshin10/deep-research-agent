from __future__ import annotations

import json
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
from bs4 import BeautifulSoup

from core.search.base import SearchHit
from core.sources.adapters.base import AdapterBrokenError, SourceAdapter
from core.sources.schemas import ProjectPlacement, RawProject, SourceKind


class DevfolioAdapter(SourceAdapter):
    """Devfolio project showcase adapter via JSON API or page extraction."""
    name = "devfolio"
    domain = "devfolio.co"
    source_kind = SourceKind.HACKATHON
    source_family = "hackathons"

    SELECTORS = {
        "title": "h1, [data-testid='project-name']",
        "tagline": "p[class*='tagline'], h2",
        "description": "div[class*='description'], section[class*='details']",
        "tech_stack": "div[class*='tag'], span[class*='badge']",
    }

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://api.devfolio.co/api/search/projects"

    def parse(self, url: str, content: str) -> RawProject:
        # Check if content is JSON
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "name" in data:
                return RawProject(
                    source_id=f"devfolio:{data.get('slug', url.split('/')[-1])}",
                    source_domain=self.domain,
                    source_kind=self.source_kind,
                    source_url=url,
                    name=data.get("name", ""),
                    tagline=data.get("tagline"),
                    description_raw=data.get("description", "") or data.get("readme", ""),
                    authors=[m.get("name", "") for m in data.get("team_members", []) if isinstance(m, dict)],
                    team_size=len(data.get("team_members", [])) or 1,
                    event_name=data.get("hackathon", {}).get("name") if isinstance(data.get("hackathon"), dict) else None,
                    placement=ProjectPlacement.WINNER if data.get("is_winner") else ProjectPlacement.NONE,
                    prize_name=data.get("prize_name"),
                    links=data.get("links", {}),
                    tags=data.get("tags", []),
                    tech_stack=data.get("tech_stack", []),
                    raw_json=data,
                )
        except json.JSONDecodeError:
            pass

        # HTML parsing fallback
        soup = BeautifulSoup(content, "html.parser")
        title_el = soup.select_one(self.SELECTORS["title"])
        if not title_el or not title_el.get_text(strip=True):
            raise AdapterBrokenError(self.name, url, f"Title selector '{self.SELECTORS['title']}' failed.")

        title = title_el.get_text(strip=True)
        tagline_el = soup.select_one(self.SELECTORS["tagline"])
        desc_el = soup.select_one(self.SELECTORS["description"])

        return RawProject(
            source_id=f"devfolio:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=title,
            tagline=tagline_el.get_text(strip=True) if tagline_el else None,
            description_raw=desc_el.get_text("\n", strip=True) if desc_el else "",
            raw_html=content[:2000],
        )


class DoraHacksAdapter(SourceAdapter):
    """DoraHacks BUIDL & Grant showcase adapter."""
    name = "dorahacks"
    domain = "dorahacks.io"
    source_kind = SourceKind.HACKATHON
    source_family = "hackathons"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://dorahacks.io/buidl"

    def parse(self, url: str, content: str) -> RawProject:
        try:
            data = json.loads(content)
            if "buidl" in data:
                b = data["buidl"]
                return RawProject(
                    source_id=f"dorahacks:{b.get('id', url.split('/')[-1])}",
                    source_domain=self.domain,
                    source_kind=self.source_kind,
                    source_url=url,
                    name=b.get("name", "Untitled BUIDL"),
                    tagline=b.get("tagline"),
                    description_raw=b.get("description", ""),
                    authors=[b.get("creator", {}).get("name", "")] if isinstance(b.get("creator"), dict) else [],
                    team_size=1,
                    placement=ProjectPlacement.WINNER if b.get("is_winner") else ProjectPlacement.NONE,
                    links={"repo": b.get("github_url", "")} if b.get("github_url") else {},
                    tags=b.get("track_names", []),
                    tech_stack=b.get("tags", []),
                )
        except Exception:
            pass

        soup = BeautifulSoup(content, "html.parser")
        title_el = soup.select_one("h1, .buidl-title")
        if not title_el:
            raise AdapterBrokenError(self.name, url, "BUIDL title selector not found.")
        return RawProject(
            source_id=f"dorahacks:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=title_el.get_text(strip=True),
            description_raw=soup.get_text(" ", strip=True)[:1000],
        )


class ETHGlobalAdapter(SourceAdapter):
    """ETHGlobal Showcase Gallery adapter."""
    name = "ethglobal"
    domain = "ethglobal.com"
    source_kind = SourceKind.HACKATHON
    source_family = "hackathons"

    SELECTORS = {
        "title": "h1",
        "tagline": "p.text-xl, div.text-gray-500",
        "description": "div.prose, #content",
        "prizes": "span[class*='badge']:has(svg), div:has(> span:contains('Winner'))",
    }

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://ethglobal.com/showcase"

    def parse(self, url: str, content: str) -> RawProject:
        soup = BeautifulSoup(content, "html.parser")
        title_el = soup.select_one(self.SELECTORS["title"])
        if not title_el or not title_el.get_text(strip=True):
            raise AdapterBrokenError(self.name, url, "ETHGlobal showcase title selector not found.")

        title = title_el.get_text(strip=True)
        desc_el = soup.select_one(self.SELECTORS["description"])
        prizes = [p.get_text(strip=True) for p in soup.select(self.SELECTORS["prizes"]) if "winner" in p.get_text(strip=True).lower()]

        links: Dict[str, str] = {}
        for a in soup.select("a[href^='http']"):
            href = a.get("href", "")
            if "github.com" in href:
                links["repo"] = href
            elif "demo" in href.lower() or "vercel.app" in href:
                links["demo"] = href

        return RawProject(
            source_id=f"ethglobal:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=title,
            description_raw=desc_el.get_text("\n", strip=True) if desc_el else "",
            placement=ProjectPlacement.WINNER if prizes else ProjectPlacement.NONE,
            prize_name="; ".join(prizes) if prizes else None,
            links=links,
        )


class MLHAdapter(SourceAdapter):
    """Major League Hacking public hackathon showcase adapter."""
    name = "mlh"
    domain = "mlh.io"
    source_kind = SourceKind.HACKATHON
    source_family = "hackathons"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://mlh.io/seasons/2026/events"

    def parse(self, url: str, content: str) -> RawProject:
        soup = BeautifulSoup(content, "html.parser")
        title_el = soup.select_one("h1, h2.event-title")
        if not title_el:
            raise AdapterBrokenError(self.name, url, "MLH event title selector not found.")
        return RawProject(
            source_id=f"mlh:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=title_el.get_text(strip=True),
            description_raw=soup.get_text(" ", strip=True)[:1000],
        )


class UnstopAdapter(SourceAdapter):
    """Unstop competitions and public innovation challenge winners."""
    name = "unstop"
    domain = "unstop.com"
    source_kind = SourceKind.HACKATHON
    source_family = "hackathons"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://unstop.com/hackathons"

    def parse(self, url: str, content: str) -> RawProject:
        soup = BeautifulSoup(content, "html.parser")
        title_el = soup.select_one("h1")
        if not title_el:
            raise AdapterBrokenError(self.name, url, "Unstop challenge title selector not found.")
        return RawProject(
            source_id=f"unstop:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=title_el.get_text(strip=True),
            description_raw=soup.get_text(" ", strip=True)[:1000],
        )


class Hack2skillAdapter(SourceAdapter):
    """Hack2skill public challenge showcase adapter."""
    name = "hack2skill"
    domain = "hack2skill.com"
    source_kind = SourceKind.HACKATHON
    source_family = "hackathons"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://hack2skill.com/hackathons"

    def parse(self, url: str, content: str) -> RawProject:
        soup = BeautifulSoup(content, "html.parser")
        title_el = soup.select_one("h1")
        if not title_el:
            raise AdapterBrokenError(self.name, url, "Hack2skill title selector not found.")
        return RawProject(
            source_id=f"hack2skill:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=title_el.get_text(strip=True),
            description_raw=soup.get_text(" ", strip=True)[:1000],
        )


class SIHAdapter(SourceAdapter):
    """Smart India Hackathon problem statement and winner list adapter."""
    name = "sih"
    domain = "sih.gov.in"
    source_kind = SourceKind.HACKATHON
    source_family = "hackathons"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://sih.gov.in/sih2026PS"

    def parse(self, url: str, content: str) -> RawProject:
        soup = BeautifulSoup(content, "html.parser")
        ps_el = soup.select_one("h4, h3, .ps-title, tr td:nth-child(2)")
        if not ps_el:
            raise AdapterBrokenError(self.name, url, "SIH problem statement selector not found.")
        return RawProject(
            source_id=f"sih:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=f"SIH Problem: {ps_el.get_text(strip=True)[:80]}",
            description_raw=soup.get_text(" ", strip=True)[:1500],
            tags=["Government", "Public Innovation", "SIH"],
        )


class KaggleAdapter(SourceAdapter):
    """Kaggle competitions and winning discussion write-up adapter."""
    name = "kaggle"
    domain = "kaggle.com"
    source_kind = SourceKind.HACKATHON
    source_family = "hackathons"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://www.kaggle.com/api/v1/competitions/list"

    def parse(self, url: str, content: str) -> RawProject:
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return RawProject(
                    source_id=f"kaggle:{data.get('ref', url.split('/')[-1])}",
                    source_domain=self.domain,
                    source_kind=self.source_kind,
                    source_url=url,
                    name=data.get("title", ""),
                    tagline=data.get("description"),
                    description_raw=data.get("evaluationMetric", "") + "\n" + data.get("description", ""),
                    placement=ProjectPlacement.WINNER if data.get("isWinner") else ProjectPlacement.NONE,
                    prize_name=data.get("reward"),
                    tags=data.get("categories", []),
                )
        except Exception:
            pass

        soup = BeautifulSoup(content, "html.parser")
        title_el = soup.select_one("h1")
        if not title_el:
            raise AdapterBrokenError(self.name, url, "Kaggle competition title selector not found.")
        return RawProject(
            source_id=f"kaggle:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=title_el.get_text(strip=True),
            description_raw=soup.get_text(" ", strip=True)[:1000],
        )


class GitHubHackathonAdapter(SourceAdapter):
    """GitHub Hackathon repository search adapter via official search API payload."""
    name = "github_hackathon"
    domain = "github.com"
    source_kind = SourceKind.HACKATHON
    source_family = "code"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://api.github.com/search/repositories?q=topic:hackathon-winner+sort:stars"

    def parse(self, url: str, content: str) -> RawProject:
        try:
            data = json.loads(content)
            # Item can be a single repo object or a search results wrapper
            repo = data["items"][0] if "items" in data and len(data["items"]) > 0 else data
            name = repo.get("name", "")
            if not name:
                raise AdapterBrokenError(self.name, url, "GitHub repo JSON missing 'name' attribute.")

            placement = ProjectPlacement.NONE
            topics = repo.get("topics", [])
            if any("winner" in t.lower() for t in topics):
                placement = ProjectPlacement.WINNER

            links = {
                "repo": repo.get("html_url", url),
                "demo": repo.get("homepage", "") if repo.get("homepage") else "",
            }

            return RawProject(
                source_id=f"github:{repo.get('id', name)}",
                source_domain=self.domain,
                source_kind=self.source_kind,
                source_url=repo.get("html_url", url),
                name=name,
                tagline=repo.get("description"),
                description_raw=repo.get("description", "") or f"GitHub repository {name}",
                authors=[repo.get("owner", {}).get("login", "")] if isinstance(repo.get("owner"), dict) else [],
                team_size=1,
                placement=placement,
                links={k: v for k, v in links.items() if v},
                tags=topics,
                tech_stack=[repo.get("language")] if repo.get("language") else topics,
                raw_json=repo,
            )
        except Exception as e:
            if isinstance(e, AdapterBrokenError):
                raise
            raise AdapterBrokenError(self.name, url, f"Failed to parse GitHub JSON payload: {str(e)}")
