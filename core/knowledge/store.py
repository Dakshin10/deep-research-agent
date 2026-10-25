from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select, or_, and_, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.knowledge.parser import DocumentParser
from core.knowledge.chunker import TextChunker
from core.knowledge.embedder import EmbeddingModel
from core.state.models import Base, DocumentModel, DocumentChunkModel


class KnowledgeStore:
    """Manages document ingestion, chunking, embedding, and hybrid vector+keyword retrieval with strict tenant isolation."""

    def __init__(
        self,
        tenant_id: Optional[str] = None,
        db_url: str = "sqlite+aiosqlite:///:memory:",
        session_factory: Optional[Any] = None,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ):
        self.tenant_id = tenant_id
        self.db_url = db_url
        self._session_factory = session_factory
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.chunker = TextChunker(chunk_size=800, chunk_overlap=100)
        self.embedder = EmbeddingModel()
        self._engine = None

    async def init_db(self):
        if self._session_factory is None:
            self._engine = create_async_engine(self.db_url, echo=False)
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def get_session(self) -> AsyncSession:
        if self._session_factory is None:
            await self.init_db()
        session: AsyncSession = self._session_factory()
        if "postgresql" in self.db_url:
            if self.tenant_id:
                await session.execute(
                    text("SET LOCAL app.tenant_id = :tenant_id"),
                    {"tenant_id": self.tenant_id},
                )
            else:
                await session.execute(text("SET LOCAL app.tenant_id = ''"))
        return session

    # -------------------------------------------------------------
    # Document Ingestion
    # -------------------------------------------------------------
    async def ingest_document(
        self,
        filename: str,
        content: bytes,
        is_benchmark: bool = False,
    ) -> str:
        # Benchmarks have tenant_id=None (shared read-only)
        doc_tenant_id = None if is_benchmark else self.tenant_id
        parsed_text = DocumentParser.parse_bytes(content, filename)
        chunks = self.chunker.chunk_text(parsed_text)

        doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        async with await self.get_session() as session:
            doc_model = DocumentModel(
                id=doc_id,
                tenant_id=doc_tenant_id,
                filename=filename,
                file_type=filename.split(".")[-1] if "." in filename else "txt",
            )
            session.add(doc_model)

            for idx, chunk_text in enumerate(chunks):
                vec = self.embedder.embed_text(chunk_text)
                chunk_model = DocumentChunkModel(
                    id=f"chk_{uuid.uuid4().hex[:8]}",
                    document_id=doc_id,
                    tenant_id=doc_tenant_id,
                    chunk_index=idx,
                    text=chunk_text,
                    embedding=vec,
                    metadata_json={"filename": filename, "is_benchmark": is_benchmark},
                )
                session.add(chunk_model)

            await session.commit()

        return doc_id

    # -------------------------------------------------------------
    # Hybrid Retrieval (Vector + Keyword)
    # -------------------------------------------------------------
    async def retrieve(
        self,
        query: str,
        top_k: int = 8,
    ) -> List[Dict[str, Any]]:
        query_vec = self.embedder.embed_text(query)
        query_words = set(re.findall(r"\w+", query.lower()))

        async with await self.get_session() as session:
            # Enforce multi-tenancy filter: either tenant's own docs or shared benchmarks (tenant_id IS NULL)
            if self.tenant_id:
                condition = or_(
                    DocumentChunkModel.tenant_id == self.tenant_id,
                    DocumentChunkModel.tenant_id.is_(None),
                )
            else:
                condition = DocumentChunkModel.tenant_id.is_(None)

            stmt = select(DocumentChunkModel).where(condition)
            res = await session.execute(stmt)
            chunks = res.scalars().all()

        scored_results = []
        for c in chunks:
            # 1. Vector similarity
            vec_sim = self.embedder.cosine_similarity(query_vec, c.embedding or [])

            # 2. Keyword overlap score
            chunk_words = set(re.findall(r"\w+", c.text.lower()))
            overlap = len(query_words.intersection(chunk_words))
            kw_score = overlap / max(1, len(query_words))

            # 3. Hybrid score
            hybrid_score = (self.vector_weight * vec_sim) + (self.keyword_weight * kw_score)

            scored_results.append({
                "chunk_id": c.id,
                "document_id": c.document_id,
                "tenant_id": c.tenant_id,
                "text": c.text,
                "score": hybrid_score,
                "vector_score": vec_sim,
                "keyword_score": kw_score,
                "is_benchmark": c.tenant_id is None,
            })

        # Rank and return top_k
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:top_k]
