import logging
import re
import tempfile
from pathlib import Path

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count
from django.http import FileResponse
from django.conf import settings

from ingestion.models import RawDocument
from ingestion.services.embedder import get_embedder
from ingestion.services.hashing import upsert_raw_document
from ingestion.services.pipeline import process_document
from query.services.retriever import search_chunks
from query.services.prompt_builder import build_prompt
from query.services.llm_client import generate_answer
from query.serializers import QueryRequestSerializer, StatsRequestSerializer


def extract_text_from_upload(file_obj):
    suffix = Path(file_obj.name).suffix.lower()

    if suffix in (".txt", ".md"):
        return file_obj.read().decode("utf-8", errors="ignore")

    if suffix == ".pdf":
        from pypdf import PdfReader
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file_obj.read())
            tmp_path = tmp.name
        try:
            reader = PdfReader(tmp_path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    if suffix == ".docx":
        import docx
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(file_obj.read())
            tmp_path = tmp.name
        try:
            document = docx.Document(tmp_path)
            return "\n".join(p.text for p in document.paragraphs)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    raise ValueError(f"Format tidak didukung: {suffix}")


def parse_yearly_document_stats(raw_text: str):
    cleaned_lines = []
    for line in raw_text.splitlines():
        stripped = re.sub(r"\s+", " ", line).strip()
        if stripped:
            cleaned_lines.append(stripped)

    rows = []
    for line in cleaned_lines:
        line_no_pipe = line.replace("|", " ")
        parts = re.split(r"\s+", line_no_pipe)
        if not parts:
            continue

        first = parts[0].strip()
        if not re.fullmatch(r"\d{4}", first):
            continue

        values = []
        for token in parts[1:]:
            token = token.strip().rstrip(".")
            if token.lower() in {"tahun", "total", "berlaku", "tidak", "berlaku", "tidakberlaku"}:
                continue
            cleaned_token = token.replace(".", "").replace(",", "")
            if re.fullmatch(r"\d+", cleaned_token):
                values.append(int(cleaned_token))

        if len(values) >= 3:
            rows.append({
                "year": int(first),
                "total": values[0],
                "berlaku": values[1],
                "tidak_berlaku": values[2],
            })

    if not rows:
        return []

    return rows


def parse_compensation_table(raw_text: str):
    text = raw_text.replace("\r", "\n")
    header_keywords = ["NO KELAS JABATAN TUNJANGAN KINERJA", "KELAS JABATAN", "TUNJANGAN KINERJA PER KELAS JABATAN"]
    header_idx = None
    for keyword in header_keywords:
        idx = text.upper().find(keyword.upper())
        if idx != -1:
            header_idx = idx
            break

    if header_idx is None:
        return []

    start = text[header_idx:]
    lines = [re.sub(r"\s+", " ", line).strip() for line in start.splitlines() if re.sub(r"\s+", " ", line).strip()]

    rows = []
    for line in lines[1:]:
        normalized = line.replace("|", " ")
        if not re.search(r"\d", normalized):
            continue

        match = re.search(r"^(?:\d+\.|\d+)\s+(\d+)\s+Rp?\s*([0-9\.,]+)(?:,\d+)?", normalized, re.I)
        if not match:
            continue

        row_no = int(match.group(1))
        amount_tokens = match.group(2).replace(".", "").replace(",", ".")
        try:
            amount = int(float(amount_tokens))
        except ValueError:
            continue

        if amount <= 0:
            continue

        rows.append({
            "no": row_no,
            "kelas_jabatan": int(match.group(1)),
            "nilai": f"Rp{int(amount):,}".replace(",", ".").replace(".", ",") if False else None,
            "nilai_raw": amount,
        })

    if not rows:
        return []

    return rows


def extract_document_tables(raw_text: str):
    tables = []
    yearly = parse_yearly_document_stats(raw_text)
    if yearly:
        tables.append({
            "title": "Jumlah PP yang Diterbitkan",
            "type": "yearly",
            "data": yearly,
        })

    comp = parse_compensation_table(raw_text)
    if comp:
        tables.append({
            "title": "Tunjangan Kinerja Per Kelas Jabatan",
            "type": "compensation",
            "data": comp,
        })

    return tables

logger = logging.getLogger(__name__)


class RootView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response(
            {
                "app": "RAG Dashboard + Chatbox",
                "status": "ok",
                "message": "API backend aktif.",
                "endpoints": {
                    "health": "/api/health/",
                    "query": "/api/query/",
                    "stats": "/api/stats/",
                    "admin": "/admin/",
                },
            },
            status=status.HTTP_200_OK,
        )


class FrontendView(APIView):
    """Serve the frontend index.html"""
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        frontend_path = settings.BASE_DIR / "frontend" / "index.html"
        if frontend_path.exists():
            return FileResponse(
                open(frontend_path, "rb"), 
                content_type="text/html"
            )
        return Response(
            {"error": "Frontend not found"},
            status=status.HTTP_404_NOT_FOUND
        )


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class QueryView(APIView):
    """
    /api/query/ - endpoint utama chatbox.
    Alur: Embed Pertanyaan -> Similarity Search -> Prompt Anti-Halusinasi -> LLM Groq -> Jawaban + Sitasi.
    """

    def post(self, request):
        serializer = QueryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        question = data["question"].strip()
        top_k = data["top_k"]

        allowed_levels = ["public", "internal"]
        if data["include_restricted"] and request.user.is_authenticated and request.user.is_staff:
            allowed_levels.append("restricted")

        try:
            embedder = get_embedder()
            query_vector = embedder.embed([question])[0]
            chunks = search_chunks(
                query_embedding=query_vector,
                top_k=top_k,
                allowed_access_levels=allowed_levels,
            )
        except Exception as exc:
            logger.exception("Embedding/retrieval failed for query")
            chunks = []
            question = question or "pertanyaan kosong"

        if not chunks:
            answer = (
                "Saya tidak menemukan informasi yang relevan di basis pengetahuan saat ini. "
                "Pastikan dokumen sudah di-ingest dan coba pertanyaan yang lebih spesifik."
            )
            return Response({
                "question": question,
                "answer": answer,
                "sources": [],
            }, status=status.HTTP_200_OK)

        messages = build_prompt(question, chunks)

        try:
            answer = generate_answer(messages)
        except Exception as exc:
            logger.exception("LLM generation failed for query")
            answer = (
                "Saya gagal menghasilkan jawaban karena layanan AI sedang tidak tersedia. "
                "Silakan coba lagi dalam beberapa saat."
            )

        return Response({
            "question": question,
            "answer": answer,
            "sources": [
                {
                    "title": c["title"],
                    "source_name": c["source_name"],
                    "source_type": c["source_type"],
                    "source_ref": c["source_ref"],
                }
                for c in chunks
            ],
        }, status=status.HTTP_200_OK)


class StatsView(APIView):
    """
    /api/stats/ - endpoint agregasi untuk grafik dashboard.
    Sumber datanya metadata raw_documents, bukan isi teksnya,
    karena ini agregasi terstruktur untuk grafik.
    """

    def get(self, request):
        serializer = StatsRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        group_by = serializer.validated_data["group_by"]

        qs = (
            RawDocument.objects
            .filter(is_active=True)
            .values(group_by)
            .annotate(total=Count("id"))
            .order_by("-total")
        )

        return Response({
            "group_by": group_by,
            "data": list(qs),
        }, status=status.HTTP_200_OK)


class UploadDocumentsView(APIView):
    """
    /api/upload/ - upload dokumen dari frontend dan langsung ingest + chunking.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        files = request.FILES.getlist("files")
        if not files:
            return Response({"error": "Tidak ada file yang dikirim."}, status=status.HTTP_400_BAD_REQUEST)

        source_name = request.POST.get("source_name", "frontend-upload")
        access_level = request.POST.get("access_level", "internal")

        ingested = []
        skipped = []
        errors = []

        for file_obj in files:
            try:
                text = extract_text_from_upload(file_obj)
            except Exception as exc:
                errors.append({"name": file_obj.name, "error": str(exc)})
                continue

            if not text.strip():
                skipped.append(file_obj.name)
                continue

            doc = upsert_raw_document(
                RawDocument,
                source_type="local",
                source_name=source_name,
                external_id=file_obj.name,
                title=file_obj.name,
                raw_content=text,
                metadata={"file_name": file_obj.name, "file_size": file_obj.size},
                access_level=access_level,
            )

            if doc is None:
                skipped.append(file_obj.name)
                continue

            try:
                process_document(doc)
                ingested.append(file_obj.name)
            except Exception as exc:
                errors.append({"name": file_obj.name, "error": f"Gagal chunking: {exc}"})

        return Response({
            "source_name": source_name,
            "ingested": ingested,
            "skipped": skipped,
            "errors": errors,
        }, status=status.HTTP_200_OK)


class DocumentStatsView(APIView):
    """
    /api/document-stats/ - ekstraksi tabel statistik dari isi dokumen,
    misalnya tahun/total/berlaku/tidak berlaku untuk PP atau tabel numerik.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        docs = []
        for doc in RawDocument.objects.filter(is_active=True).order_by("-created_at"):
            tables = extract_document_tables(doc.raw_content or "")
            if tables:
                primary = tables[0]
                docs.append({
                    "title": doc.title or doc.external_id,
                    "source_name": doc.source_name,
                    "source_type": doc.source_type,
                    "data": primary["data"],
                    "tables": tables,
                })

        return Response({
            "docs": docs,
            "count": len(docs),
        }, status=status.HTTP_200_OK)
