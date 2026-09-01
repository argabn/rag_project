"""
Retriever: similarity search top-k + filter skor + filter access_level.
Setara dengan node 'Similarity Search top-k + filter skor (pgvector)'.
"""
from pgvector.django import CosineDistance
from ingestion.models import DocumentChunk


def search_chunks(query_embedding: list[float], top_k: int = 5,
                   score_threshold: float = 0.6, allowed_access_levels=None):
    """
    score_threshold adalah ambang MAX cosine distance yang diterima.
    Karena embeddings dibaca dengan normalize_embeddings=True, jarak relevan
    untuk dokumen yang benar sering berada di kisaran 0.3–0.6, bukan < 0.35.
    allowed_access_levels: daftar access_level yang boleh diakses user.
    Default hanya 'public' + 'internal'; 'restricted' harus eksplisit
    diizinkan oleh caller (mis. hanya untuk user staff).
    """
    allowed_access_levels = allowed_access_levels or ["public", "internal"]

    qs = (
        DocumentChunk.objects
        .filter(raw_document__is_active=True)
        .filter(raw_document__access_level__in=allowed_access_levels)
        .annotate(distance=CosineDistance("embedding", query_embedding))
        .order_by("distance")[:top_k]
    )

    results = []
    for chunk in qs:
        if chunk.distance > score_threshold:
            continue
        results.append({
            "chunk_id": str(chunk.id),
            "content": chunk.content,
            "distance": float(chunk.distance),
            "source_name": chunk.raw_document.source_name,
            "source_type": chunk.raw_document.source_type,
            "source_ref": chunk.raw_document.source_ref,
            "title": chunk.raw_document.title,
        })
    return results
