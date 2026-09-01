from django.core.management.base import BaseCommand
from ingestion.models import RawDocument
from ingestion.services.integrator import Integrator
from ingestion.services.hashing import upsert_raw_document


class Command(BaseCommand):
    help = "Ingest dokumen dari satu atau banyak sumber API terdaftar di Integrator."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            action="append",
            dest="sources",
            help="Nama sumber spesifik (bisa diulang). Kosongkan untuk semua sumber.",
        )

    def handle(self, *args, **options):
        integrator = Integrator(source_names=options.get("sources"))

        total_new, total_skip, total_error = 0, 0, 0

        for source_name, cfg, items in integrator.fetch_all():
            if isinstance(items, dict) and "error" in items:
                self.stderr.write(self.style.ERROR(f"[{source_name}] gagal fetch: {items['error']}"))
                total_error += 1
                continue

            field_map = cfg["field_map"]
            access_level = cfg.get("access_level", "internal")

            for item in items:
                external_id = str(item.get(field_map["id"], ""))
                title = str(item.get(field_map["title"], ""))
                raw_content = str(item.get(field_map["raw_content"], ""))

                if not raw_content:
                    continue

                doc = upsert_raw_document(
                    RawDocument,
                    source_type="api",
                    source_name=source_name,
                    external_id=external_id,
                    title=title,
                    raw_content=raw_content,
                    metadata={"raw_item_keys": list(item.keys())},
                    access_level=access_level,
                )

                if doc:
                    total_new += 1
                else:
                    total_skip += 1

            self.stdout.write(f"[{source_name}] selesai diproses ({len(items)} item)")

        self.stdout.write(self.style.SUCCESS(
            f"ingest_api selesai. Baru/update: {total_new}, tidak berubah: {total_skip}, error sumber: {total_error}"
        ))
