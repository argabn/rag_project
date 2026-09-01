from pathlib import Path
from django.core.management.base import BaseCommand
from ingestion.models import RawDocument
from ingestion.services.hashing import upsert_raw_document


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if suffix == ".docx":
        import docx
        d = docx.Document(str(path))
        return "\n".join(p.text for p in d.paragraphs)

    raise ValueError(f"Format tidak didukung: {suffix}")


class Command(BaseCommand):
    help = "Ingest dokumen dari folder lokal (pdf/docx/txt/md)."

    def add_arguments(self, parser):
        parser.add_argument("path", type=str, help="Path ke folder berisi dokumen")
        parser.add_argument(
            "--source-name", type=str, default="local-files",
            help="Label sumber, tersimpan di source_name",
        )
        parser.add_argument(
            "--access-level", type=str, default="internal",
            choices=["public", "internal", "restricted"],
        )

    def handle(self, *args, **options):
        folder = Path(options["path"])
        if not folder.exists():
            self.stderr.write(self.style.ERROR(f"Folder tidak ditemukan: {folder}"))
            return

        supported = {".pdf", ".docx", ".txt", ".md"}
        files = [f for f in folder.rglob("*") if f.suffix.lower() in supported]

        total_new, total_skip, total_error = 0, 0, 0

        for f in files:
            try:
                text = extract_text(f)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Gagal baca {f.name}: {e}"))
                total_error += 1
                continue

            if not text.strip():
                continue

            doc = upsert_raw_document(
                RawDocument,
                source_type="local",
                source_name=options["source_name"],
                external_id=str(f.relative_to(folder)),
                title=f.name,
                raw_content=text,
                metadata={"file_path": str(f), "file_size": f.stat().st_size},
                access_level=options["access_level"],
            )

            if doc:
                total_new += 1
            else:
                total_skip += 1

        self.stdout.write(self.style.SUCCESS(
            f"ingest_local selesai. Baru/update: {total_new}, tidak berubah: {total_skip}, error: {total_error}"
        ))
