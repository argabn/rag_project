import hashlib


def hash_content(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def upsert_raw_document(model, *, source_type, source_name, external_id,
                         title, raw_content, metadata=None, access_level="internal"):
    """
    Logika dedup/versioning:
    - Kalau content_hash sama dgn versi aktif terakhir -> skip, return None.
    - Kalau beda -> nonaktifkan versi lama, buat versi baru.
    - Kalau belum ada sama sekali -> buat versi 1.
    """
    new_hash = hash_content(raw_content)

    existing = (
        model.objects.filter(
            source_type=source_type,
            source_name=source_name,
            external_id=external_id,
            is_active=True,
        )
        .order_by("-version")
        .first()
    )

    if existing and existing.content_hash == new_hash:
        return None  # tidak ada perubahan, skip

    next_version = (existing.version + 1) if existing else 1

    if existing:
        existing.is_active = False
        existing.save(update_fields=["is_active"])

    doc = model.objects.create(
        source_type=source_type,
        source_name=source_name,
        external_id=external_id,
        version=next_version,
        content_hash=new_hash,
        title=title,
        raw_content=raw_content,
        metadata=metadata or {},
        access_level=access_level,
        is_active=True,
    )
    return doc
