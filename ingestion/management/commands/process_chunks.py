from django.core.management.base import BaseCommand
from ingestion.services.pipeline import process_pending_documents, process_document
from ingestion.models import RawDocument


class Command(BaseCommand):
    help = "Proses chunking + embedding untuk raw_documents yang belum diproses."

    def add_arguments(self, parser):
        parser.add_argument(
            "--doc-id", type=str, default=None,
            help="Proses satu dokumen spesifik by UUID (opsional).",
        )
        parser.add_argument("--chunk-size", type=int, default=500)
        parser.add_argument("--overlap", type=int, default=50)

    def handle(self, *args, **options):
        chunk_size = options["chunk_size"]
        overlap = options["overlap"]

        if options["doc_id"]:
            doc = RawDocument.objects.get(id=options["doc_id"])
            n = process_document(doc, chunk_size=chunk_size, overlap=overlap)
            self.stdout.write(self.style.SUCCESS(f"Dokumen {doc.id}: {n} chunk dibuat"))
            return

        total_docs, total_chunks = process_pending_documents(
            chunk_size=chunk_size, overlap=overlap
        )
        self.stdout.write(self.style.SUCCESS(
            f"process_chunks selesai. {total_docs} dokumen diproses, {total_chunks} chunk dibuat."
        ))
