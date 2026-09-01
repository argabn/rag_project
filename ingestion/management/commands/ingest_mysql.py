from django.core.management.base import BaseCommand
from django.conf import settings
from ingestion.models import RawDocument
from ingestion.services.hashing import upsert_raw_document


class Command(BaseCommand):
    help = "Ingest dokumen dari database MySQL eksternal."

    def add_arguments(self, parser):
        parser.add_argument("--table", type=str, required=True, help="Nama tabel sumber di MySQL")
        parser.add_argument("--id-column", type=str, default="id")
        parser.add_argument("--title-column", type=str, default="title")
        parser.add_argument("--content-column", type=str, required=True)
        parser.add_argument("--source-name", type=str, default="mysql-source")
        parser.add_argument(
            "--access-level", type=str, default="internal",
            choices=["public", "internal", "restricted"],
        )

    def handle(self, *args, **options):
        import pymysql

        conn = pymysql.connect(
            host=settings.MYSQL_SOURCE["HOST"],
            user=settings.MYSQL_SOURCE["USER"],
            password=settings.MYSQL_SOURCE["PASSWORD"],
            database=settings.MYSQL_SOURCE["NAME"],
            port=settings.MYSQL_SOURCE.get("PORT", 3306),
            cursorclass=pymysql.cursors.DictCursor,
        )

        table = options["table"]
        id_col = options["id_column"]
        title_col = options["title_column"]
        content_col = options["content_column"]

        total_new, total_skip = 0, 0

        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT * FROM `{table}`")
                rows = cursor.fetchall()

            for row in rows:
                raw_content = str(row.get(content_col, ""))
                if not raw_content.strip():
                    continue

                doc = upsert_raw_document(
                    RawDocument,
                    source_type="mysql",
                    source_name=options["source_name"],
                    external_id=str(row.get(id_col, "")),
                    title=str(row.get(title_col, "")),
                    raw_content=raw_content,
                    metadata={"table": table, "row_keys": list(row.keys())},
                    access_level=options["access_level"],
                )

                if doc:
                    total_new += 1
                else:
                    total_skip += 1
        finally:
            conn.close()

        self.stdout.write(self.style.SUCCESS(
            f"ingest_mysql selesai. Baru/update: {total_new}, tidak berubah: {total_skip}"
        ))
