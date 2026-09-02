from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from ingestion.models import RawDocument


class RAGProjectSecurityAndHealthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="tester",
            password="secret123",
        )

    def test_health_endpoint_is_public(self):
        response = self.client.get(reverse("api-health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")

    def test_root_path_returns_info_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("RAG Dashboard", response.content.decode("utf-8"))

    def test_query_is_public_for_local_demo(self):
        response = self.client.post(
            reverse("api-query"),
            {"question": "Apa itu dokumen?"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("tidak menemukan informasi yang relevan", response.data["answer"].lower())

    def test_stats_endpoint_is_public(self):
        response = self.client.get(reverse("api-stats"), {"group_by": "source_type"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("group_by", response.data)

    def test_authenticated_query_without_context_returns_semantic_fallback(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            reverse("api-query"),
            {"question": "Apa isi dokumen ini?"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("tidak menemukan informasi yang relevan", response.data["answer"].lower())

    def test_document_stats_endpoint_extracts_yearly_table_from_document_content(self):
        RawDocument.objects.create(
            source_type="local",
            source_name="test-doc",
            external_id="pp-2020-2023.txt",
            title="Data PP Tahun 2020-2023",
            raw_content=(
                "Tahun Total Berlaku Tidak Berlaku\n"
                "2020 81 77 4\n"
                "2021 122 121 1\n"
                "2022 59 58 1\n"
                "2023 55 55 0"
            ),
            content_hash="abc123",
            access_level="internal",
            metadata={},
        )

        response = self.client.get(reverse("api-document-stats"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("docs", response.data)
        self.assertGreater(len(response.data["docs"][0]["data"]), 0)
        self.assertEqual(response.data["docs"][0]["data"][0]["year"], 2020)
