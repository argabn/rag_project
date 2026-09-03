import os, sys, django
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, str(Path(__file__).parent))
django.setup()

from ingestion.models import RawDocument
from ingestion.services.document_extractor import (
    extract_pdf_figures,
    extract_adaptive_tables,
    extract_adaptive_charts,
)

docs = RawDocument.objects.filter(is_active=True)
print(f"Total dokumen aktif: {docs.count()}")

for doc in docs:
    meta = doc.metadata or {}
    file_path = meta.get("file_path", "")
    if not file_path or not file_path.endswith(".pdf"):
        print(f"SKIP (bukan PDF): {doc.title}")
        continue

    p = Path(file_path)
    if not p.exists():
        print(f"SKIP (file tidak ada): {file_path}")
        continue

    if meta.get("tables") and meta.get("charts"):
        print(f"SKIP (sudah lengkap): {doc.title} - {len(meta['tables'])} tables, {len(meta['charts'])} charts")
        continue

    print(f"Processing: {doc.title}...", flush=True)

    try:
        figures_meta = meta.get("figures") or []
        if not figures_meta:
            extracted_figs = extract_pdf_figures(p, doc_id=str(doc.id), doc_title=doc.title, use_llm=False)
            figures_meta = [
                {"id": fg["id"], "title": fg["title"], "caption": fg["caption"],
                 "page": fg["page"], "category": fg["category"], "image_url": fg["image_url"],
                 "width": fg.get("width"), "height": fg.get("height"),
                 "doc_title": fg.get("doc_title", doc.title),
                 "analysis": fg.get("analysis", ""), "insights": fg.get("insights", []),
                 "suggested_questions": fg.get("suggested_questions", [])}
                for fg in extracted_figs
            ]

        tables_meta = extract_adaptive_tables(p, doc_id=str(doc.id), doc_title=doc.title, use_llm=False)
        charts_meta = extract_adaptive_charts(p, doc_id=str(doc.id), doc_title=doc.title, tables=tables_meta, use_llm=False)

        doc.metadata = {
            **meta,
            "file_path": str(p), "file_size": p.stat().st_size,
            "figures": figures_meta, "figures_count": len(figures_meta),
            "tables": tables_meta, "tables_count": len(tables_meta),
            "charts": charts_meta, "charts_count": len(charts_meta),
        }
        doc.save(update_fields=["metadata"])
        print(f"  OK: {len(tables_meta)} tables, {len(charts_meta)} charts, {len(figures_meta)} figures")

    except Exception as exc:
        import traceback
        print(f"  ERROR: {exc}")
        traceback.print_exc()

print("\nSelesai!")
