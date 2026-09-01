from django.contrib import admin
from ingestion.models import RawDocument, DocumentChunk


@admin.register(RawDocument)
class RawDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title", "source_type", "source_name", "version",
        "is_active", "access_level", "ingested_at",
    )
    list_filter = ("source_type", "source_name", "is_active", "access_level")
    search_fields = ("title", "external_id", "raw_content")
    readonly_fields = ("id", "content_hash", "created_at", "updated_at", "ingested_at")


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("raw_document", "chunk_index", "embedding_model", "token_count", "created_at")
    list_filter = ("embedding_model",)
    search_fields = ("content",)
    readonly_fields = ("id", "created_at")
