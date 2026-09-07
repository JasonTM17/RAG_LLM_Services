"""Document ingestion pipeline wiring storage, parsing, normalization, chunking, and embedding."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from rag_llm_services_api.db.models.document_chunk import DocumentChunkModel
from rag_llm_services_api.domain.documents import DocumentStatus, IngestionJobStatus
from rag_llm_services_api.infrastructure.repositories.chunks import (
    ChunkCreateData,
    ChunkRepository,
)
from rag_llm_services_api.infrastructure.repositories.documents import DocumentRepository
from rag_llm_services_api.infrastructure.storage.base import ObjectStoragePort
from rag_llm_services_embeddings.base import EmbeddingProvider
from rag_llm_services_rag.chunking import Chunker
from rag_llm_services_rag.normalization import TextNormalizer
from rag_llm_services_rag.parsers.base import ParsedDocument
from rag_llm_services_rag.parsers.registry import ParserRegistry, get_default_parser_registry
from rag_llm_services_shared.errors import NotFoundError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    """Outcome of an ingestion pipeline run."""

    document_id: UUID
    version_id: UUID
    chunk_count: int
    status: DocumentStatus
    error_message: str | None = None


class IngestionPipeline:
    """End-to-end ingestion pipeline turning stored raw documents into vectorized chunks.

    Sequence:
    ObjectStoragePort -> ParserRegistry -> TextNormalizer -> Chunker -> EmbeddingProvider -> ChunkRepository
    """

    def __init__(
        self,
        object_storage: ObjectStoragePort,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        embedding_provider: EmbeddingProvider,
        parser_registry: ParserRegistry | None = None,
        normalizer: TextNormalizer | None = None,
        chunker: Chunker | None = None,
    ) -> None:
        self._storage = object_storage
        self._doc_repo = document_repo
        self._chunk_repo = chunk_repo
        self._embeddings = embedding_provider
        self._parser_registry = parser_registry or get_default_parser_registry()
        self._normalizer = normalizer or TextNormalizer()
        self._chunker = chunker or Chunker()

    async def _transition_status(
        self,
        owner_id: UUID,
        document_id: UUID,
        job_id: UUID | None,
        doc_status: DocumentStatus,
        job_status: IngestionJobStatus,
        error_message: str | None = None,
    ) -> None:
        """Safely record status updates for document and associated ingestion job."""
        await self._doc_repo.update_document_status(
            owner_id=owner_id,
            doc_id=document_id,
            status=doc_status.value,
            error_message=error_message,
        )
        if job_id:
            await self._doc_repo.update_ingestion_job_status(
                owner_id=owner_id,
                job_id=job_id,
                status=job_status.value,
                error_message=error_message,
            )

    async def ingest_document(
        self,
        owner_id: UUID,
        document_id: UUID,
        version_id: UUID | None = None,
        job_id: UUID | None = None,
    ) -> IngestionResult:
        """Execute the ingestion pipeline for a document version.

        Updates document and job statuses across lifecycle stages and transactionally
        persists vector embeddings.
        """
        # 1. Fetch document
        doc = await self._doc_repo.get_document_by_id(owner_id, document_id)
        if doc is None:
            raise NotFoundError(f"Document '{document_id}' not found for owner '{owner_id}'")

        # Resolve target version
        target_version = None
        if version_id:
            for v in doc.versions:
                if v.id == version_id:
                    target_version = v
                    break
        elif doc.current_version_id:
            for v in doc.versions:
                if v.id == doc.current_version_id:
                    target_version = v
                    break

        if target_version is None:
            raise NotFoundError(f"No valid version found for document '{document_id}'")

        actual_version_id = target_version.id
        storage_key = target_version.storage_key
        mime_type = target_version.mime_type
        doc_filename = doc.filename

        try:
            # 2. Status: PARSING (or PROCESSING)
            await self._transition_status(
                owner_id,
                document_id,
                job_id,
                DocumentStatus.PARSING,
                IngestionJobStatus.PARSING,
            )

            # 3. Read object from storage
            raw_bytes = await self._storage.get_object(storage_key)

            # 4. Select parser & parse (outside API event loop)
            parser = self._parser_registry.select_by_mime_and_sniff(
                mime_type,
                filename=doc_filename,
                content=raw_bytes,
            )
            parsed_doc = await asyncio.to_thread(parser.parse, raw_bytes, filename=doc_filename)

            # 5. Status: CHUNKING
            await self._transition_status(
                owner_id,
                document_id,
                job_id,
                DocumentStatus.CHUNKING,
                IngestionJobStatus.CHUNKING,
            )

            # 6. Normalize text and sections
            normalized_sections = self._normalizer.normalize_sections(parsed_doc.sections)
            normalized_doc = ParsedDocument(
                raw_text=self._normalizer.normalize(parsed_doc.raw_text),
                sections=normalized_sections,
                metadata=dict(parsed_doc.metadata),
            )

            # 7. Semantic chunking
            chunks = self._chunker.chunk_document(normalized_doc)

            # 8. Status: EMBEDDING
            await self._transition_status(
                owner_id,
                document_id,
                job_id,
                DocumentStatus.EMBEDDING,
                IngestionJobStatus.EMBEDDING,
            )

            chunk_models: list[DocumentChunkModel] = []
            if chunks:
                # 9. Generate dense embeddings in batches
                texts_to_embed = [c.content for c in chunks]
                embeddings = await self._embeddings.embed_documents(texts_to_embed)

                # 10. Prepare ChunkCreateData
                chunk_data_list: list[ChunkCreateData] = []
                for chunk, vector in zip(chunks, embeddings):
                    chunk_data_list.append(
                        ChunkCreateData(
                            chunk_index=chunk.chunk_index,
                            content=chunk.content,
                            token_count=chunk.token_count,
                            metadata_json=chunk.metadata,
                            embedding=vector,
                        )
                    )

                # 11. Transactional chunk replacement for idempotent re-indexing
                chunk_models = await self._chunk_repo.replace_document_chunks_transactionally(
                    owner_id=owner_id,
                    document_id=document_id,
                    document_version_id=actual_version_id,
                    chunks_data=chunk_data_list,
                )
            else:
                # If no chunks were generated (e.g. empty or non-text document)
                await self._chunk_repo.replace_document_chunks_transactionally(
                    owner_id=owner_id,
                    document_id=document_id,
                    document_version_id=actual_version_id,
                    chunks_data=[],
                )

            # 12. Status: INDEXED
            await self._transition_status(
                owner_id,
                document_id,
                job_id,
                DocumentStatus.INDEXED,
                IngestionJobStatus.INDEXED,
                error_message=None,
            )

            return IngestionResult(
                document_id=document_id,
                version_id=actual_version_id,
                chunk_count=len(chunk_models),
                status=DocumentStatus.INDEXED,
            )

        except Exception as exc:
            err_msg = str(exc) or type(exc).__name__
            logger.exception("Ingestion failed for document %s: %s", document_id, err_msg)
            # Record failure state in database safely
            try:
                await self._transition_status(
                    owner_id,
                    document_id,
                    job_id,
                    DocumentStatus.FAILED,
                    IngestionJobStatus.FAILED,
                    error_message=err_msg,
                )
            except Exception as update_err:  # noqa: BLE001
                logger.error("Failed to update status to FAILED: %s", update_err)

            return IngestionResult(
                document_id=document_id,
                version_id=actual_version_id,
                chunk_count=0,
                status=DocumentStatus.FAILED,
                error_message=err_msg,
            )
