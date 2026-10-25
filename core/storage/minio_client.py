from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional


class MinIOStorageService:
    """Object storage client for MinIO (S3 API) with local fallback."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
        secure: Optional[bool] = None,
    ):
        self.endpoint = endpoint or os.environ.get("MINIO_ENDPOINT", "localhost:9000")
        self.access_key = access_key or os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = secret_key or os.environ.get("MINIO_SECRET_KEY", "minioadmin")
        self.bucket_name = bucket_name or os.environ.get("MINIO_BUCKET", "deep-research-artifacts")
        self.secure = secure if secure is not None else (os.environ.get("MINIO_SECURE", "false").lower() == "true")

        self.client = None
        self._local_fallback_dir = Path("artifacts_storage")
        self._init_client()

    def _init_client(self):
        try:
            from minio import Minio
            import urllib3
            http_client = urllib3.PoolManager(
                timeout=urllib3.Timeout(connect=1.0, read=2.0),
                retries=urllib3.Retry(total=1, backoff_factor=0.2),
            )
            self.client = Minio(
                endpoint=self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
                http_client=http_client,
            )
            # Create bucket if it doesn't exist
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
        except Exception:
            # Fallback to local storage directory
            self.client = None
            self._local_fallback_dir.mkdir(parents=True, exist_ok=True)

    def upload_artifact(
        self,
        job_id: str,
        artifact_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        object_name = f"{job_id}/{artifact_name}"

        if self.client:
            try:
                self.client.put_object(
                    bucket_name=self.bucket_name,
                    object_name=object_name,
                    data=io.BytesIO(data),
                    length=len(data),
                    content_type=content_type,
                )
                protocol = "https" if self.secure else "http"
                return f"{protocol}://{self.endpoint}/{self.bucket_name}/{object_name}"
            except Exception:
                pass

        # Local storage fallback
        dest_path = self._local_fallback_dir / job_id / artifact_name
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(data)
        return str(dest_path.resolve())

    def get_artifact(self, job_id: str, artifact_name: str) -> Optional[bytes]:
        object_name = f"{job_id}/{artifact_name}"
        if self.client:
            try:
                response = self.client.get_object(self.bucket_name, object_name)
                return response.read()
            except Exception:
                pass

        local_path = self._local_fallback_dir / job_id / artifact_name
        if local_path.exists():
            with open(local_path, "rb") as f:
                return f.read()
        return None
