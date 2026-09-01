import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count

from ingestion.models import RawDocument
from ingestion.services.embedder import get_embedder
from query.services.retriever import search_chunks
from query.services.prompt_builder import build_prompt
from query.services.llm_client import generate_answer
from query.serializers import QueryRequestSerializer, StatsRequestSerializer

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
