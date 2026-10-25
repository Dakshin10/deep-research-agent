from __future__ import annotations

import json
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
import feedparser

from core.sources.adapters.base import AdapterBrokenError, SourceAdapter
from core.sources.schemas import ProjectPlacement, RawProject, SourceKind


class DevToAdapter(SourceAdapter):
    """Dev.to / Forem articles and hackathon build logs adapter."""
    name = "devto"
    domain = "dev.to"
    source_kind = SourceKind.BLOG
    source_family = "writeups"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://dev.to/api/articles?tag=hackathon&per_page=50"

    def parse(self, url: str, content: str) -> RawProject:
        try:
            data = json.loads(content)
            article = data[0] if isinstance(data, list) and len(data) > 0 else data
            title = article.get("title", "")
            if not title:
                raise AdapterBrokenError(self.name, url, "Dev.to article JSON missing 'title'.")

            return RawProject(
                source_id=f"devto:{article.get('id', title[:20])}",
                source_domain=self.domain,
                source_kind=self.source_kind,
                source_url=article.get("url", url),
                name=title,
                tagline=article.get("description"),
                description_raw=article.get("body_markdown", "") or article.get("description", "") or title,
                authors=[article.get("user", {}).get("name", "")] if isinstance(article.get("user"), dict) else [],
                links={"canonical": article.get("canonical_url", "")},
                tags=article.get("tag_list", []) if isinstance(article.get("tag_list"), list) else [],
                tech_stack=article.get("tag_list", []) if isinstance(article.get("tag_list"), list) else [],
                raw_json=article,
            )
        except Exception as e:
            if isinstance(e, AdapterBrokenError):
                raise
            raise AdapterBrokenError(self.name, url, f"Failed to parse Dev.to article: {str(e)}")


class HashnodeAdapter(SourceAdapter):
    """Hashnode developer project write-up adapter."""
    name = "hashnode"
    domain = "hashnode.com"
    source_kind = SourceKind.BLOG
    source_family = "writeups"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://api.hashnode.com"

    def parse(self, url: str, content: str) -> RawProject:
        try:
            data = json.loads(content)
            post = data.get("post") or data.get("data", {}).get("post") or data
            title = post.get("title", "")
            if not title:
                raise AdapterBrokenError(self.name, url, "Hashnode post JSON missing 'title'.")

            return RawProject(
                source_id=f"hashnode:{post.get('id', title[:20])}",
                source_domain=self.domain,
                source_kind=self.source_kind,
                source_url=url,
                name=title,
                tagline=post.get("brief"),
                description_raw=post.get("content", {}).get("markdown", "") if isinstance(post.get("content"), dict) else post.get("brief", ""),
                authors=[post.get("author", {}).get("name", "")] if isinstance(post.get("author"), dict) else [],
                tags=[t.get("name") for t in post.get("tags", []) if isinstance(t, dict)],
                raw_json=post,
            )
        except Exception as e:
            if isinstance(e, AdapterBrokenError):
                raise
            raise AdapterBrokenError(self.name, url, f"Failed to parse Hashnode JSON: {str(e)}")


class RSSWriteupsAdapter(SourceAdapter):
    """RSS Feed adapter for Medium, Substack, and tech publications."""
    name = "rss_writeups"
    domain = "medium.com"
    source_kind = SourceKind.BLOG
    source_family = "writeups"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://medium.com/feed/tag/hackathon"

    def parse(self, url: str, content: str) -> RawProject:
        feed = feedparser.parse(content)
        if not feed.entries:
            raise AdapterBrokenError(self.name, url, "RSS feed contains zero valid entries.")

        entry = feed.entries[0]
        title = entry.get("title", "")
        summary = entry.get("summary", "") or entry.get("description", "")

        return RawProject(
            source_id=f"rss:{entry.get('id', title[:20])}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=entry.get("link", url),
            name=title,
            description_raw=summary,
            authors=[entry.get("author", "")] if entry.get("author") else [],
            tags=[t.get("term") for t in entry.get("tags", []) if isinstance(t, dict)],
        )


class YouTubePitchesAdapter(SourceAdapter):
    """YouTube demo and pitch video adapter with yt-dlp metadata and transcript extraction."""
    name = "youtube_pitches"
    domain = "youtube.com"
    source_kind = SourceKind.VIDEO
    source_family = "video"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://www.youtube.com/results?search_query=hackathon+winner+pitch+demo"

    def parse(self, url: str, content: str) -> RawProject:
        # Check if content is a serialized JSON containing yt-dlp metadata or transcript
        try:
            data = json.loads(content)
            title = data.get("title", "")
            if not title:
                raise AdapterBrokenError(self.name, url, "YouTube JSON missing video 'title'.")

            description = data.get("description", "")
            transcript_text = data.get("transcript_text", "")
            full_text = f"{description}\n\n[Transcript]\n{transcript_text}" if transcript_text else description

            return RawProject(
                source_id=f"youtube:{data.get('id', url.split('=')[-1])}",
                source_domain=self.domain,
                source_kind=self.source_kind,
                source_url=data.get("webpage_url", url),
                name=title,
                tagline=f"YouTube Demo/Pitch video by {data.get('uploader', 'Unknown')}",
                description_raw=full_text or title,
                authors=[data.get("uploader", "")] if data.get("uploader") else [],
                links={"video": data.get("webpage_url", url)},
                tags=data.get("tags", []),
                raw_json=data,
            )
        except Exception as e:
            if isinstance(e, AdapterBrokenError):
                raise
            raise AdapterBrokenError(self.name, url, f"Failed to parse YouTube payload: {str(e)}")

    def extract_transcript(self, video_id: str) -> str:
        """Helper to extract transcript via youtube_transcript_api if available."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            return " ".join([item["text"] for item in transcript_list])
        except Exception:
            return ""


class PDFReportsAdapter(SourceAdapter):
    """PyMuPDF extractor for PDF pitch decks, SIH problem statements, and hackathon winner lists."""
    name = "pdf_reports"
    domain = "sih.gov.in"
    source_kind = SourceKind.PAPER
    source_family = "academic"

    async def discover(self, limit: int = 50, since_year: Optional[int] = None) -> AsyncGenerator[str, None]:
        yield "https://sih.gov.in/pdf/SIH2026_Problem_Statements.pdf"

    def parse(self, url: str, content: str) -> RawProject:
        # Content passed can be raw extracted text with page headers or a path
        if not content or len(content.strip()) < 10:
            raise AdapterBrokenError(self.name, url, "PDF document text is empty or unreadable.")

        lines = [line.strip() for line in content.split("\n") if line.strip()]
        title = lines[0] if lines else "PDF Report Project"

        return RawProject(
            source_id=f"pdf:{url.split('/')[-1]}",
            source_domain=self.domain,
            source_kind=self.source_kind,
            source_url=url,
            name=title[:100],
            description_raw=content[:5000],
            tags=["PDF", "Pitch Deck", "Report"],
        )
