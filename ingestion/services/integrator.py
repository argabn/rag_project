"""
Integrator: agregator konfigurasi banyak sumber API.
Setiap sumber didefinisikan sebagai dict config, supaya nambah API baru
tinggal nambah entri di API_SOURCES tanpa mengubah command ingest_api.
"""
import requests
from django.conf import settings


API_SOURCES = {
    "e-office": {
        "url": "https://eoffice.internal/api/documents",
        "method": "GET",
        "headers": {"Authorization": f"Bearer {settings.EOFFICE_TOKEN}"},
        "params": {},
        # mapping field respons API -> field RawDocument
        "field_map": {
            "id": "external_id",
            "judul": "title",
            "isi": "raw_content",
        },
        "access_level": "internal",
    },
    "simpeg": {
        "url": "https://simpeg.internal/api/pegawai",
        "method": "GET",
        "headers": {"Authorization": f"Bearer {settings.SIMPEG_TOKEN}"},
        "params": {},
        "field_map": {
            "nip": "external_id",
            "nama": "title",
            "detail": "raw_content",
        },
        "access_level": "restricted",  # data kepegawaian -> restricted
    },
    "arsip-digital": {
        "url": "https://arsip.internal/api/records",
        "method": "GET",
        "headers": {"Authorization": f"Bearer {settings.ARSIP_TOKEN}"},
        "params": {},
        "field_map": {
            "record_id": "external_id",
            "nama_arsip": "title",
            "konten": "raw_content",
        },
        "access_level": "internal",
    },
    # tambah "API N" di sini, tanpa ubah command ingest_api.py
}


class Integrator:
    """Menjalankan fetch untuk satu atau semua sumber API yang terdaftar."""

    def __init__(self, source_names=None):
        self.sources = (
            {k: API_SOURCES[k] for k in source_names if k in API_SOURCES}
            if source_names
            else API_SOURCES
        )

    def fetch_all(self):
        """Yield tuple (source_name, cfg, list_of_raw_items) per sumber."""
        for name, cfg in self.sources.items():
            try:
                items = self._fetch_one(cfg)
                yield name, cfg, items
            except requests.RequestException as e:
                yield name, cfg, {"error": str(e)}

    def _fetch_one(self, cfg):
        resp = requests.request(
            method=cfg["method"],
            url=cfg["url"],
            headers=cfg.get("headers", {}),
            params=cfg.get("params", {}),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("results", [])
