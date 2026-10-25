from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict, List, Optional
from bs4 import BeautifulSoup

from core.sources.adapters.base import AdapterBrokenError, SourceAdapter
from core.sources.schemas import ProjectPlacement, RawProject, SourceKind


class YCAdapter(SourceAdapter):
    """Y Combinator public company directory adapter."""
    name = "yc"
    domain = "ycombinator.com"
    source_kind = SourceKind.STARTUP
    source_family = "startups"

    SELECTORS = {
        "title": "h1.font-bold, h1",
        "tagline": "div.text-xl, div[class*='tagline']",
        "description": "div.prose, div[class*='description']",
        "batch": "span:contains('Y Combinator Logo'), a[href*='batch=']",
        "founders": "div[class*='founder'] h3, div.leading-snug.font-bold",
    }

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://www.ycombinator.com/companies"

    def parse(self, url: str, content: str) -> RawProject:
        soup = BeautifulSoup(content, "html.parser")
        title_el = soup.select_one(self.SELECTORS["title"])
        if not title_el or not title_el.get_text(strip=True):
            raise AdapterBrokenError(self.name, url, "YC company name selector not found.")

        title = title_el.get_text(strip=True)
        tagline_el = soup.select_one(self.SELECTORS["tagline"])
        desc_el = soup.select_one(self.SELECTORS["description"])

        links: Dict[str, str] = {}
        website_el = soup.select_one("a[href^='http']:not([href*='ycombinator.com'])")
        if website_el:
            links["website"] = website_el.get("href", "")

        return RawProject(
            source_id=f"yc:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=title,
            tagline=tagline_el.get_text(strip=True) if tagline_el else None,
            description_raw=desc_el.get_text("\n", strip=True) if desc_el else "",
            links=links,
            tags=["YC", "Startup"],
        )


class ProductHuntAdapter(SourceAdapter):
    """Product Hunt official API and HTML adapter."""
    name = "producthunt"
    domain = "producthunt.com"
    source_kind = SourceKind.LAUNCH
    source_family = "launches"

    SELECTORS = {
        "title": "h1[data-test='post-name'], h1",
        "tagline": "h2[data-test='post-tagline'], div.text-xl",
        "description": "div[data-test='post-description'], article",
        "upvotes": "[data-test='vote-button'] span, [class*='upvote']",
    }

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://api.producthunt.com/v2/api/graphql"

    def parse(self, url: str, content: str) -> RawProject:
        try:
            data = json.loads(content)
            post = data.get("post") or data.get("data", {}).get("post") or data
            if "name" in post:
                return RawProject(
                    source_id=f"ph:{post.get('id', post['name'])}",
                    source_domain=self.domain,
                    source_kind=self.source_kind,
                    source_url=url,
                    name=post.get("name", ""),
                    tagline=post.get("tagline"),
                    description_raw=post.get("description", "") or post.get("tagline", ""),
                    links={"website": post.get("website", "")} if post.get("website") else {},
                    tags=[t.get("name") for t in post.get("topics", []) if isinstance(t, dict)],
                    raw_json=post,
                )
        except Exception:
            pass

        soup = BeautifulSoup(content, "html.parser")
        title_el = soup.select_one(self.SELECTORS["title"])
        if not title_el:
            raise AdapterBrokenError(self.name, url, "Product Hunt post title selector not found.")

        title = title_el.get_text(strip=True)
        tagline_el = soup.select_one(self.SELECTORS["tagline"])
        desc_el = soup.select_one(self.SELECTORS["description"])

        return RawProject(
            source_id=f"ph:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=title,
            tagline=tagline_el.get_text(strip=True) if tagline_el else None,
            description_raw=desc_el.get_text("\n", strip=True) if desc_el else "",
        )


class HNLaunchesAdapter(SourceAdapter):
    """Hacker News 'Show HN' and 'Launch HN' adapter via Algolia Search API."""
    name = "hn_launches"
    domain = "news.ycombinator.com"
    source_kind = SourceKind.LAUNCH
    source_family = "launches"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://hn.algolia.com/api/v1/search?tags=(story,show_hn)&hitsPerPage=50"

    def parse(self, url: str, content: str) -> RawProject:
        try:
            data = json.loads(content)
            hit = data["hits"][0] if "hits" in data and len(data["hits"]) > 0 else data
            title = hit.get("title", "")
            if not title:
                raise AdapterBrokenError(self.name, url, "HN Algolia hit missing 'title' field.")

            clean_name = title.replace("Show HN:", "").replace("Launch HN:", "").strip()
            links: Dict[str, str] = {}
            if hit.get("url"):
                links["website"] = hit["url"]
            links["hn_discussion"] = f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"

            return RawProject(
                source_id=f"hn:{hit.get('objectID', clean_name)}",
                source_domain=self.domain,
                source_kind=self.source_kind,
                source_url=url,
                name=clean_name,
                tagline=f"Show HN submission with {hit.get('points', 0)} points and {hit.get('num_comments', 0)} comments",
                description_raw=hit.get("story_text", "") or hit.get("comment_text", "") or title,
                authors=[hit.get("author", "")] if hit.get("author") else [],
                links=links,
                tags=["Hacker News", "Show HN", "Launch"],
                raw_json=hit,
            )
        except Exception as e:
            if isinstance(e, AdapterBrokenError):
                raise
            raise AdapterBrokenError(self.name, url, f"Failed to parse HN Algolia JSON: {str(e)}")


class BetaListAdapter(SourceAdapter):
    """BetaList startup launches adapter."""
    name = "betalist"
    domain = "betalist.com"
    source_kind = SourceKind.STARTUP
    source_family = "startups"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://betalist.com/feed"

    def parse(self, url: str, content: str) -> RawProject:
        soup = BeautifulSoup(content, "html.parser")
        title_el = soup.select_one("h1, .startup__title")
        if not title_el:
            raise AdapterBrokenError(self.name, url, "BetaList startup title selector not found.")

        tagline_el = soup.select_one("h2, .startup__pitch")
        desc_el = soup.select_one(".startup__description, article")

        return RawProject(
            source_id=f"betalist:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=title_el.get_text(strip=True),
            tagline=tagline_el.get_text(strip=True) if tagline_el else None,
            description_raw=desc_el.get_text("\n", strip=True) if desc_el else "",
        )


class IndieHackersAdapter(SourceAdapter):
    """Indie Hackers milestone and product post adapter."""
    name = "indiehackers"
    domain = "indiehackers.com"
    source_kind = SourceKind.STARTUP
    source_family = "startups"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://www.indiehackers.com/products"

    def parse(self, url: str, content: str) -> RawProject:
        soup = BeautifulSoup(content, "html.parser")
        title_el = soup.select_one("h1, .product-header__name")
        if not title_el:
            raise AdapterBrokenError(self.name, url, "Indie Hackers product name selector not found.")

        desc_el = soup.select_one(".product-header__tagline, .product-story, .post-body")

        return RawProject(
            source_id=f"indiehackers:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=title_el.get_text(strip=True),
            description_raw=desc_el.get_text("\n", strip=True) if desc_el else "",
        )


class RedditStartupsAdapter(SourceAdapter):
    """Reddit public JSON API adapter for r/startups, r/SideProject, r/SaaS."""
    name = "reddit_startups"
    domain = "reddit.com"
    source_kind = SourceKind.STARTUP
    source_family = "startups"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        for sub in ["startups", "SideProject", "SaaS"]:
            yield f"https://www.reddit.com/r/{sub}/top.json?t=month&limit=50"

    def parse(self, url: str, content: str) -> RawProject:
        try:
            data = json.loads(content)
            # Handle post object from JSON API
            if isinstance(data, list) and len(data) > 0:
                post = data[0]["data"]["children"][0]["data"]
            elif "data" in data and "children" in data["data"] and len(data["data"]["children"]) > 0:
                post = data["data"]["children"][0]["data"]
            elif "data" in data and "title" in data["data"]:
                post = data["data"]
            else:
                post = data

            title = post.get("title", "")
            if not title:
                raise AdapterBrokenError(self.name, url, "Reddit JSON post missing 'title'.")

            return RawProject(
                source_id=f"reddit:{post.get('id', title[:20])}",
                source_domain=self.domain,
                source_kind=self.source_kind,
                source_url=url,
                name=title,
                tagline=f"r/{post.get('subreddit', 'startups')} discussion with {post.get('score', 0)} upvotes",
                description_raw=post.get("selftext", "") or title,
                authors=[post.get("author", "")] if post.get("author") else [],
                links={"reddit": f"https://reddit.com{post.get('permalink', '')}"},
                tags=[post.get("subreddit", "startups"), "Reddit"],
                raw_json=post,
            )
        except Exception as e:
            if isinstance(e, AdapterBrokenError):
                raise
            raise AdapterBrokenError(self.name, url, f"Failed to parse Reddit post JSON: {str(e)}")
