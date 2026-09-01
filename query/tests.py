from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient


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
