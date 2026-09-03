import copy
import logging
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from ingestion.models import RawDocument
from ingestion.services.document_extractor import (
    extract_adaptive_charts,
    extract_adaptive_tables,
    extract_pdf_figures,
)


logger = logging.getLogger(__name__)


def _figure_metadata(figure):
    return {
        "id": figure["id"],
        "title": figure["title"],
        "caption": figure["caption"],
        "page": figure["page"],
        "category": figure["category"],
        "image_url": figure["image_url"],
        "width": figure.get("width"),
        "height": figure.get("height"),
        "doc_title": figure.get("doc_title", ""),
        "analysis": figure.get("analysis", ""),
        "insights": figure.get("insights", []),
        "suggested_questions": figure.get("suggested_questions", []),
    }


def _is_fallback_analysis(analysis, context):
    analysis = (analysis or "").lower()
    if context == "figure":
        return analysis.startswith("bagan visual asli pada halaman")
    return analysis.startswith("tabel data terstruktur dari dokumen")


class Command(BaseCommand):
    help = "Regenerate figure/table/chart metadata for active local PDF documents."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delay",
            type=float,
            default=8.0,
            help="Delay in seconds between LLM calls to avoid TPM rate limits.",
        )

    def handle(self, *args, **options):
        documents = RawDocument.objects.filter(
            is_active=True,
            source_type="local",
        ).order_by("id")
        cached_metadata = {}
        processed = 0
        failed = 0
        delay = max(0.0, options["delay"])

        for document in documents:
            file_path = (document.metadata or {}).get("file_path", "")
            if Path(file_path).suffix.lower() != ".pdf":
                continue

            path = Path(file_path)
            if not path.is_absolute():
                path = settings.BASE_DIR / path
            path = path.resolve()

            if not path.exists():
                failed += 1
                self.stderr.write(self.style.ERROR(
                    f"[{document.id}] dilewati: file tidak ditemukan {path}"
                ))
                continue

            try:
                if str(path) not in cached_metadata:
                    figures = extract_pdf_figures(
                        path,
                        doc_id=str(document.id),
                        doc_title=document.title,
                        use_llm=True,
                        llm_limit=None,
                        llm_delay=delay,
                    )
                    if delay:
                        time.sleep(delay)
                    tables = extract_adaptive_tables(
                        path,
                        doc_id=str(document.id),
                        doc_title=document.title,
                        use_llm=True,
                        llm_limit=None,
                        llm_delay=delay,
                    )
                    if delay:
                        time.sleep(delay)
                    charts = extract_adaptive_charts(
                        path,
                        doc_id=str(document.id),
                        doc_title=document.title,
                        tables=tables,
                        use_llm=True,
                    )
                    cached_metadata[str(path)] = {
                        "figures": [_figure_metadata(figure) for figure in figures],
                        "tables": tables,
                        "charts": charts,
                    }

                regenerated = copy.deepcopy(cached_metadata[str(path)])
                metadata = dict(document.metadata or {})
                metadata.update({
                    "file_path": metadata.get("file_path", file_path),
                    "figures_count": len(regenerated["figures"]),
                    "figures": regenerated["figures"],
                    "tables_count": len(regenerated["tables"]),
                    "tables": regenerated["tables"],
                    "charts_count": len(regenerated["charts"]),
                    "charts": regenerated["charts"],
                })
                document.metadata = metadata
                document.save(update_fields=["metadata", "updated_at"])

                fallback_figures = sum(
                    _is_fallback_analysis(figure.get("analysis"), "figure")
                    for figure in regenerated["figures"]
                )
                fallback_tables = sum(
                    _is_fallback_analysis(table.get("analysis"), "table")
                    for table in regenerated["tables"]
                )
                total_items = len(regenerated["figures"]) + len(regenerated["tables"])
                fallback_items = fallback_figures + fallback_tables
                if fallback_items:
                    message = (
                        f"[{document.id}] metadata ditulis, fallback "
                        f"{fallback_items}/{total_items}; lihat log exception LLM "
                        "untuk penyebab per item"
                    )
                    logger.warning(message)
                    self.stdout.write(self.style.WARNING(message))
                else:
                    message = (
                        f"[{document.id}] berhasil generate analisa asli "
                        f"({total_items} item)"
                    )
                    logger.info(message)
                    self.stdout.write(self.style.SUCCESS(message))
                processed += 1
            except Exception:
                failed += 1
                logger.exception("[%s] reprocess metadata gagal", document.id)
                self.stderr.write(self.style.ERROR(
                    f"[{document.id}] gagal; traceback ditulis ke logs/app.log"
                ))

        self.stdout.write(self.style.SUCCESS(
            f"reprocess_metadata selesai: {processed} berhasil, {failed} gagal, "
            f"{len(cached_metadata)} PDF unik"
        ))