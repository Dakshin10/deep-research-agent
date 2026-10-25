from __future__ import annotations

import hashlib
import re
import urllib.parse
from typing import Dict, List, Optional, Set, Tuple

from core.search.base import SearchHit

# Common tracking / click identification parameters to strip
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "msclkid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
    "_ga",
    "_gl",
    "yclid",
    "dclid",
    "wbraid",
    "gbraid",
}


def normalize_canonical_url(url: str) -> str:
    """
    Normalizes a URL to a canonical format:
    1. Trims whitespace and parses scheme/netloc.
    2. Lowercases scheme and hostname.
    3. Drops default HTTP/HTTPS ports.
    4. Strips marketing/click tracking query parameters.
    5. Sorts query parameters deterministically.
    6. Normalizes trailing slashes on paths.
    7. Strips page anchor fragments.
    """
    if not url:
        return ""

    url = url.strip()
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return url

    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()

    # Strip default ports
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    path = parsed.path or "/"
    # Clean redundant consecutive slashes in path
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    # Filter and sort query parameters
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    cleaned_params = [
        (k.lower(), v)
        for k, v in query_params
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    cleaned_params.sort(key=lambda x: (x[0], x[1]))
    new_query = urllib.parse.urlencode(cleaned_params)

    # Reconstruct without anchor fragments
    return urllib.parse.urlunsplit((scheme, netloc, path, new_query, ""))


class SimHash:
    """
    Pure Python 64-bit SimHash implementation for near-duplicate text detection.
    Computes Hamming distance between two texts without requiring compiled C-extensions.
    """

    @staticmethod
    def _hash_token(token: str) -> int:
        # Use md5 to produce a deterministic 64-bit integer
        digest = hashlib.md5(token.encode("utf-8")).digest()
        # Take first 8 bytes as unsigned 64-bit integer
        return int.from_bytes(digest[:8], byteorder="big", signed=False)

    @classmethod
    def compute(cls, text: str) -> int:
        if not text:
            return 0

        clean = re.sub(r"\s+", " ", text.lower().strip())
        if len(clean) < 3:
            tokens = [clean]
        else:
            # Character 3-grams provide robust similarity for typos, plurals, and minor word shifts
            tokens = [clean[i:i+3] for i in range(len(clean) - 2)]

        v = [0] * 64
        for token in tokens:
            h = cls._hash_token(token)
            for i in range(64):
                bit = (h >> i) & 1
                v[i] += 1 if bit == 1 else -1

        fingerprint = 0
        for i in range(64):
            if v[i] > 0:
                fingerprint |= (1 << i)

        return fingerprint

    @staticmethod
    def hamming_distance(h1: int, h2: int) -> int:
        """Counts differing bits between two 64-bit fingerprints."""
        xor = (h1 ^ h2) & 0xFFFFFFFFFFFFFFFF
        return bin(xor).count("1")

    @classmethod
    def is_near_duplicate(cls, text1: str, text2: str, max_distance: int = 8) -> bool:
        """Returns True if two texts have a Hamming distance <= max_distance."""
        if not text1 or not text2:
            return False
        h1 = cls.compute(text1)
        h2 = cls.compute(text2)
        if h1 == 0 or h2 == 0:
            return False
        return cls.hamming_distance(h1, h2) <= max_distance


def reciprocal_rank_fusion(
    ranked_lists: List[List[SearchHit]],
    k: int = 60,
    max_simhash_distance: int = 3,
) -> List[SearchHit]:
    """
    Merges multiple ranked lists using Reciprocal Rank Fusion (RRF):
      RRF_score(d) = SUM(1.0 / (k + rank_in_list))
    Deduplicates by canonical URL and filters near-duplicate snippets using SimHash.
    """
    scores: Dict[str, float] = {}
    best_hit: Dict[str, SearchHit] = {}
    seen_simhashes: List[Tuple[int, str]] = []  # (simhash, canonical_url)

    for r_list in ranked_lists:
        for rank, hit in enumerate(r_list, 1):
            canon_url = normalize_canonical_url(hit.url)
            hit.canonical_url = canon_url

            # Compute RRF score contribution
            score_delta = 1.0 / (k + rank)
            scores[canon_url] = scores.get(canon_url, 0.0) + score_delta

            if canon_url not in best_hit:
                best_hit[canon_url] = hit
            else:
                # Merge snippet if other has longer excerpt
                current = best_hit[canon_url]
                if len(hit.snippet or "") > len(current.snippet or ""):
                    current.snippet = hit.snippet
                if hit.published_at and not current.published_at:
                    current.published_at = hit.published_at

    # Sort candidates by combined RRF score
    sorted_urls = sorted(scores.keys(), key=lambda u: scores[u], reverse=True)

    deduped_hits: List[SearchHit] = []
    for rank, url in enumerate(sorted_urls, 1):
        hit = best_hit[url]
        hit.raw_score = scores[url]
        hit.rank = rank

        # Near-duplicate content check using SimHash
        content_text = f"{hit.title} {hit.snippet}"
        fprint = SimHash.compute(content_text)
        is_content_dupe = False
        if fprint != 0:
            for existing_fprint, _ in seen_simhashes:
                if SimHash.hamming_distance(fprint, existing_fprint) <= max_simhash_distance:
                    is_content_dupe = True
                    break

        if not is_content_dupe:
            if fprint != 0:
                seen_simhashes.append((fprint, url))
            deduped_hits.append(hit)

    return deduped_hits
