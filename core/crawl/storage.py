from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
import gzip


class RawDocumentStore:
    """
    Stores and retrieves raw fetched HTML/JSON/PDF documents.
    Backing store: MinIO/S3 if configured, or local compressed file store.
    Guarantees that any extracted field can be re-verified against raw bytes later.
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or os.path.join("data", "raw_documents"))
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def store_document(
        self,
        url: str,
        content: str | bytes,
        content_type: str = "text/html",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str]:
        """
        Stores document content keyed by SHA-256 hash.
        Returns: (content_hash, storage_path)
        """
        raw_bytes = content.encode("utf-8") if isinstance(content, str) else content
        content_hash = hashlib.sha256(raw_bytes).hexdigest()

        # Shard by first 2 chars
        sub_dir = self.base_dir / content_hash[:2]
        sub_dir.mkdir(parents=True, exist_ok=True)

        data_file = sub_dir / f"{content_hash}.gz"
        meta_file = sub_dir / f"{content_hash}.meta.json"

        # Compress and write
        with gzip.open(data_file, "wb") as f:
            f.write(raw_bytes)

        meta = {
            "content_hash": content_hash,
            "url": url,
            "content_type": content_type,
            "size_bytes": len(raw_bytes),
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        return content_hash, str(data_file)

    def get_document(self, content_hash: str) -> Optional[tuple[bytes, Dict[str, Any]]]:
        """Retrieves raw document bytes and metadata by SHA-256 hash."""
        sub_dir = self.base_dir / content_hash[:2]
        data_file = sub_dir / f"{content_hash}.gz"
        meta_file = sub_dir / f"{content_hash}.meta.json"

        if not data_file.exists():
            return None

        with gzip.open(data_file, "rb") as f:
            raw_bytes = f.read()

        meta = {}
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        return raw_bytes, meta

    def has_document(self, content_hash: str) -> bool:
        sub_dir = self.base_dir / content_hash[:2]
        return (sub_dir / f"{content_hash}.gz").exists()
