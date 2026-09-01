"""
Pipeline: raw_documents -> chunking -> embedding -> document_chunks.
Setara dengan alur 'baca raw -> Proses Chunking -> Embedding Model -> simpan chunk+vector'.
"""
from django.db import transaction
from ingestion.models import RawDocument, DocumentChunk
from ingestion.services.chunker import chunk_text
from ingestion.services.embedder import get_embedder


def process_document(raw_doc: RawDocument, embedder=None, chunk_size=500, overlap=50):
    """
    Memproses satu RawDocument: hapus chunk lama (kalau ada), buat chunk baru + embedding.
    Idempotent: aman dipanggil ulang untuk dokumen yang sama.
    """
    embedder = embedder or get_embedder()

    pieces = chunk_text(raw_doc.raw_content, chunk_size=chunk_size, overlap=overlap)
    if not pieces:
        return 0

    vectors = embedder.embed(pieces)

    with transaction.atomic():
        DocumentChunk.objects.filter(raw_document=raw_doc).delete()

        objs = [
            DocumentChunk(
                raw_document=raw_doc,
                chunk_index=i,
                content=piece,
                token_count=len(piece.split()),
                embedding=vector,
                embedding_model=embedder.model_name,
            )
            for i, (piece, vector) in enumerate(zip(pieces, vectors))
        ]
        DocumentChunk.objects.bulk_create(objs)

    return len(objs)


def cleanup_inactive_chunks():
    """
    Hapus semua DocumentChunk yang raw_document induknya sudah is_active=False.
    Memastikan similarity search tidak pernah mengembalikan konten dari
    versi dokumen yang sudah usang.
    """
    deleted, _ = DocumentChunk.objects.filter(raw_document__is_active=False).delete()
    return deleted


def process_pending_documents(batch_size=20, **kwargs):
    """
    Memproses semua RawDocument aktif yang belum punya chunk sama sekali,
    atau yang chunk-nya masih dari embedding_model lama (perlu re-embed).
    """
    embedder = get_embedder()

    docs_without_chunks = RawDocument.objects.filter(
        is_active=True, chunks__isnull=True
    ).distinct()

    docs_outdated_embedding = RawDocument.objects.filter(
        is_active=True, chunks__embedding_model__isnull=False
    ).exclude(chunks__embedding_model=embedder.model_name).distinct()

    to_process = (docs_without_chunks | docs_outdated_embedding).distinct()

    total_docs, total_chunks = 0, 0
    for doc in to_process.iterator(chunk_size=batch_size):
        n = process_document(doc, embedder=embedder, **kwargs)
        total_docs += 1
        total_chunks += n

    cleanup_inactive_chunks()
    return total_docs, total_chunks
