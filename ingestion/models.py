import uuid
from django.db import models
from pgvector.django import VectorField, HnswIndex
from django.conf import settings


class RawDocument(models.Model):
    """
    Menyimpan dokumen mentah dari semua sumber (API, lokal, MySQL).
    Setara dengan node 'Warehouse: tabel raw_documents' di diagram.
    """

    SOURCE_TYPE_CHOICES = [
        ("api", "API"),
        ("local", "Local File"),
        ("mysql", "MySQL"),
    ]

    ACCESS_LEVEL_CHOICES = [
        ("public", "Public"),
        ("internal", "Internal"),
        ("restricted", "Restricted"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # --- traceability ---
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES)
    source_name = models.CharField(max_length=100)
    source_ref = models.CharField(max_length=500, blank=True)

    # --- dedup & versioning ---
    content_hash = models.CharField(max_length=64, db_index=True)
    external_id = models.CharField(max_length=255, blank=True, db_index=True)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    # --- konten ---
    title = models.CharField(max_length=500, blank=True)
    raw_content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)

    # --- akses & sensitivitas ---
    access_level = models.CharField(
        max_length=20, choices=ACCESS_LEVEL_CHOICES, default="internal"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ingested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "raw_documents"
        indexes = [
            models.Index(fields=["source_type", "source_name"]),
            models.Index(fields=["is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_type", "source_name", "external_id", "version"],
                name="uniq_source_version",
            )
        ]

    def __str__(self):
        return f"[{self.source_name}] {self.title or self.id}"


class DocumentChunk(models.Model):
    """
    Menyimpan potongan teks + vector embedding.
    Setara dengan node 'Warehouse: tabel document_chunks (pgvector)' di diagram.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    raw_document = models.ForeignKey(
        RawDocument, on_delete=models.CASCADE, related_name="chunks"
    )

    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    token_count = models.PositiveIntegerField(default=0)

    embedding = VectorField(dimensions=settings.EMBEDDING_DIM)
    embedding_model = models.CharField(max_length=100, default="bge-m3")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "document_chunks"
        constraints = [
            models.UniqueConstraint(
                fields=["raw_document", "chunk_index"], name="uniq_chunk_per_doc"
            )
        ]
        indexes = [
            HnswIndex(
                name="chunk_embedding_hnsw_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self):
        return f"{self.raw_document_id} chunk#{self.chunk_index}"
