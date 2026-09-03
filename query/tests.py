from pathlib import Path
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from ingestion.models import RawDocument
from ingestion.services.document_extractor import (
    extract_adaptive_tables,
    extract_adaptive_charts,
    extract_pdf_figures,
    _compute_table_key_stats,
    _parse_num,
)


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
        content = (
            b"".join(response.streaming_content).decode("utf-8")
            if hasattr(response, "streaming_content")
            else response.content.decode("utf-8")
        )
        self.assertIn("Dashboard", content)

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
                "| Tahun | Total | Berlaku | Tidak Berlaku |\n"
                "| --- | --- | --- | --- |\n"
                "| 2020 | 81 | 77 | 4 |\n"
                "| 2021 | 122 | 121 | 1 |\n"
                "| 2022 | 59 | 58 | 1 |\n"
                "| 2023 | 55 | 55 | 0 |"
            ),
            content_hash="abc123",
            access_level="internal",
            metadata={},
        )

        response = self.client.get(reverse("api-document-stats"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")
        self.assertIn("tables", response.data)
        self.assertIn("charts", response.data)
        self.assertGreaterEqual(len(response.data["tables"]), 1)
        table = response.data["tables"][0]
        self.assertEqual(table["total_rows"], 4)
        self.assertEqual(table["rows"][0][0], "2020")
        self.assertEqual(table["rows"][0][1], "81")

    def test_generic_non_ham_document_extraction(self):
        """Uji bahwa dokumen non-HAM diekstrak secara akurat tanpa data HAM hardcoded."""
        raw_finance_text = (
            "| Periode | Pendapatan | Pengeluaran | Laba Bersih |\n"
            "| --- | --- | --- | --- |\n"
            "| Q1 2024 | Rp 150.000.000 | Rp 90.000.000 | Rp 60.000.000 |\n"
            "| Q2 2024 | Rp 180.000.000 | Rp 100.000.000 | Rp 80.000.000 |\n"
            "| Q3 2024 | Rp 210.000.000 | Rp 110.000.000 | Rp 100.000.000 |\n"
            "| Q4 2024 | Rp 250.000.000 | Rp 120.000.000 | Rp 130.000.000 |"
        )
        tables = extract_adaptive_tables(raw_finance_text, doc_id="fin_001", doc_title="Laporan Keuangan PT ABC")
        self.assertEqual(len(tables), 1)
        tbl = tables[0]
        self.assertEqual(tbl["total_rows"], 4)
        self.assertEqual(tbl["source"], "Laporan Keuangan PT ABC")
        self.assertIn("Pendapatan", tbl["columns"])

        # Verifikasi key_stats
        self.assertIn("Rp 250.000.000", tbl["key_stats"]["highest"])
        self.assertIn("Rp 150.000.000", tbl["key_stats"]["lowest"])

        # Verifikasi charts dari tabel keuangan
        charts = extract_adaptive_charts(raw_finance_text, doc_id="fin_001", doc_title="Laporan Keuangan PT ABC", tables=tables)
        self.assertEqual(len(charts), 1)
        ch = charts[0]
        self.assertEqual(ch["labels"], ["Q1 2024", "Q2 2024", "Q3 2024", "Q4 2024"])
        self.assertEqual(len(ch["datasets"]), 3)
        self.assertEqual(ch["datasets"][0]["data"], [150000000.0, 180000000.0, 210000000.0, 250000000.0])

    def test_empty_document_returns_empty_results_no_fabrication(self):
        """Dokumen tanpa tabel atau angka tidak boleh membuat tabel/grafik palsu."""
        plain_text = "Ini adalah dokumen narasi teks biasa tanpa tabel dan tanpa grafik apapun. Hanya berupa kalimat panjang."
        tables = extract_adaptive_tables(plain_text, doc_id="doc_plain", doc_title="Dokumen Polos")
        charts = extract_adaptive_charts(plain_text, doc_id="doc_plain", doc_title="Dokumen Polos", tables=tables)
        self.assertEqual(tables, [])
        self.assertEqual(charts, [])

    def test_pdfplumber_extraction_on_sample_pdf(self):
        """Uji ekstraksi tabel nyata dari file PDF sampel menggunakan pdfplumber."""
        pdf_path = Path("dokumen/68e32aa73b84b.pdf")
        if pdf_path.exists():
            tables = extract_adaptive_tables(pdf_path, doc_id="permen8", doc_title="Permen HAM No. 8/2025")
            self.assertGreaterEqual(len(tables), 1)
            tbl = tables[0]
            self.assertIn("KELAS JABATAN", [c.upper() for c in tbl["columns"]])
            self.assertEqual(tbl["total_rows"], 17)
            self.assertIn("Rp 33.240.000", tbl["key_stats"]["highest"])
