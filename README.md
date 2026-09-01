# RAG Dashboard + Chatbox — Multi-Source Ingestion

Sistem RAG (Retrieval-Augmented Generation) dengan dua alur utama:

1. **Flow Ingestion** — menarik data dari banyak sumber (API, file lokal, MySQL),
   menyimpannya sebagai dokumen mentah, lalu memecah dan mengubahnya jadi vector
   embedding untuk pencarian semantik (similarity search).
2. **Flow Query** — dashboard + chatbox yang menjawab pertanyaan user berdasarkan
   dokumen yang sudah di-ingest, lengkap dengan sitasi sumber, serta menampilkan
   grafik statistik dokumen.

Stack: **Django + Django REST Framework + PostgreSQL (Supabase) + pgvector + Groq LLM**.

---

## 1. Struktur Project

```
rag_project/
├── manage.py
├── requirements.txt
├── .env.example
├── config/                  # Django project settings
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── ingestion/                # App: ingestion & warehouse (raw_documents, document_chunks)
│   ├── models.py
│   ├── admin.py
│   ├── services/
│   │   ├── integrator.py     # agregator konfigurasi multi-API
│   │   ├── hashing.py        # dedup & versioning
│   │   ├── chunker.py        # pemecah teks
│   │   ├── embedder.py       # abstraksi provider embedding
│   │   └── pipeline.py       # orkestrasi chunking + embedding
│   └── management/commands/
│       ├── ingest_api.py
│       ├── ingest_local.py
│       ├── ingest_mysql.py
│       └── process_chunks.py
├── query/                    # App: RAG query & stats (chatbox + dashboard API)
│   ├── views.py               # /api/query/, /api/stats/
│   ├── urls.py
│   ├── serializers.py
│   └── services/
│       ├── retriever.py       # similarity search (pgvector)
│       ├── prompt_builder.py  # prompt anti-halusinasi
│       └── llm_client.py      # client Groq
└── frontend/
    └── index.html             # contoh dashboard + chatbox minimal (HTML/JS polos)
```

---

## 2. Prasyarat

- Python 3.11+
- Akun **Supabase** (atau Postgres lain yang mendukung extension `pgvector`)
- Akun **Groq** untuk API key LLM
- (Opsional) Akses ke sumber API internal (e-office, SIMPEG, arsip digital), file lokal, dan/atau database MySQL yang ingin di-ingest

---

## 3. Instalasi

### 3.1. Clone / salin project, lalu buat virtual environment

```bash
cd rag_project
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3.2. Install dependencies

```bash
pip install -r requirements.txt
```

> Catatan: `sentence-transformers` akan mengunduh model `BAAI/bge-m3` (~2GB) saat pertama kali dipakai. Pastikan koneksi internet stabil, atau ganti provider embedding di `.env` bila perlu (lihat bagian 4).

### 3.3. Setup environment variables

```bash
cp .env.example .env
```

Lalu edit `.env` dan isi minimal:

```
DATABASE_URL=postgresql://postgres:[PASSWORD]@[SUPABASE_HOST]:5432/postgres
GROQ_API_KEY=isi-dengan-api-key-groq-anda
EMBEDDING_PROVIDER=bge-m3
EMBEDDING_DIM=1024
```

Field lain (`EOFFICE_TOKEN`, `SIMPEG_TOKEN`, `ARSIP_TOKEN`, `MYSQL_SOURCE_*`) diisi sesuai sumber data yang ingin dipakai — boleh dikosongkan kalau sumber tersebut belum dipakai.

### 3.4. Aktifkan extension `pgvector` di Supabase

Buka **SQL Editor** di dashboard Supabase, lalu jalankan:

```sql
create extension if not exists vector;
```

Ini wajib dilakukan **sebelum** migrasi Django, karena Django tidak punya privilege untuk membuat extension di Postgres.

### 3.5. Jalankan migrasi database

```bash
python manage.py makemigrations ingestion
python manage.py migrate
```

### 3.6. (Opsional) Buat superuser untuk akses Django admin

```bash
python manage.py createsuperuser
```

Admin panel bisa dipakai untuk melihat isi `raw_documents` dan `document_chunks` secara langsung di `/admin/`.

---

## 4. Konfigurasi Sumber Data

### 4.1. Sumber API

Edit `ingestion/services/integrator.py`, bagian `API_SOURCES`, untuk menyesuaikan:
- `url` endpoint API sumber (e-office, SIMPEG, arsip digital, dst.)
- `field_map` — pemetaan nama field di respons API ke field `RawDocument` (`external_id`, `title`, `raw_content`)
- `access_level` — `public`, `internal`, atau `restricted` (SIMPEG sebaiknya `restricted`)

Untuk menambah sumber API baru ("API N"), cukup tambahkan entri baru di dictionary `API_SOURCES` — tidak perlu mengubah command `ingest_api.py`.

### 4.2. Provider Embedding

Default memakai `bge-m3` yang dijalankan lokal lewat `sentence-transformers`. Untuk memakai provider eksternal (API embedding pihak ketiga), ubah di `.env`:

```
EMBEDDING_PROVIDER=external
EXTERNAL_EMBEDDING_ENDPOINT=https://provider-anda/v1/embeddings
EXTERNAL_EMBEDDING_API_KEY=xxxxx
```

Pastikan `EMBEDDING_DIM` di `.env` sesuai dengan dimensi vector dari model yang dipakai (bge-m3 = 1024).

---

## 5. Menjalankan Ingestion (Build/Update Data)

Jalankan salah satu atau semua command berikut sesuai sumber yang tersedia:

```bash
# Ingest dari semua sumber API terdaftar
python manage.py ingest_api

# Ingest dari sumber API tertentu saja
python manage.py ingest_api --source simpeg

# Ingest dari folder lokal (pdf/docx/txt/md)
python manage.py ingest_local /path/ke/folder/dokumen --source-name arsip-manual

# Ingest dari tabel MySQL eksternal
python manage.py ingest_mysql --table pegawai --content-column detail --source-name db-pegawai
```

Semua command di atas otomatis menangani **dedup & versioning** — menjalankan ulang command yang sama tidak akan menduplikasi data; hanya membuat versi baru jika kontennya berubah.

Setelah data masuk ke `raw_documents`, jalankan proses chunking + embedding:

```bash
python manage.py process_chunks
```

Command ini akan:
- Memecah teks tiap dokumen baru menjadi chunk
- Membuat vector embedding untuk tiap chunk
- Menyimpannya ke tabel `document_chunks`
- Membersihkan chunk dari versi dokumen yang sudah tidak aktif

Untuk memproses ulang satu dokumen tertentu saja:

```bash
python manage.py process_chunks --doc-id <uuid-dokumen>
```

> **Alur update data:** setiap kali ada data baru/berubah di sumber, jalankan ulang command `ingest_*` yang relevan, lalu `process_chunks`. Bisa dijadwalkan lewat cron job sesuai kebutuhan.

---

## 6. Menjalankan Server

```bash
python manage.py runserver
```

Server berjalan di `http://localhost:8000`.

### 6.1. Endpoint yang tersedia

| Endpoint         | Method | Fungsi                                      |
|-------------------|--------|----------------------------------------------|
| `/api/query/`      | POST   | Chatbox — tanya jawab berbasis RAG           |
| `/api/stats/`      | GET    | Statistik/agregasi dokumen untuk grafik      |
| `/admin/`           | GET    | Django admin panel                           |

### 6.2. Contoh test lewat curl

```bash
curl -X POST http://localhost:8000/api/query/ \
  -H "Content-Type: application/json" \
  -d '{"question": "Apa isi surat edaran terbaru dari e-office?", "top_k": 5}'

curl "http://localhost:8000/api/stats/?group_by=source_type"
```

Contoh respons `/api/query/`:

```json
{
  "question": "Apa isi surat edaran terbaru dari e-office?",
  "answer": "Berdasarkan [Sumber 1] ...",
  "sources": [
    {
      "title": "Surat Edaran No. 123",
      "source_name": "e-office",
      "source_type": "api",
      "source_ref": ""
    }
  ]
}
```

---

## 7. Menjalankan Dashboard + Chatbox (Frontend Contoh)

Frontend demo sudah diperbarui dan tersedia di `frontend/index.html`. File ini menampilkan:

- panel dashboard dengan ringkasan statistik dokumen,
- grafik distribusi berdasarkan `source_type`,
- chatbox interaktif untuk mengirim pertanyaan ke `/api/query/`,
- status koneksi ke server Django,
- penanganan error yang lebih ramah saat API tidak aktif atau memerlukan autentikasi.

Langkah demo:

1. Pastikan server Django sedang berjalan di `http://localhost:8000`.
2. Buka `frontend/index.html` langsung di browser (double-click, atau via live preview / local web server).
3. Panel kiri menampilkan statistik dokumen dari `/api/stats/`.
4. Panel kanan adalah chatbox — ketik pertanyaan, jawaban beserta daftar sumber akan muncul, lalu statistik otomatis refresh setelah jawaban diproses.

> Untuk demo lokal, pastikan `CORS_ALLOWED_ORIGINS` atau `DJANGO_ALLOWED_HOSTS` sudah diset sesuai host browser Anda. Jika `REST_FRAMEWORK` memakai `IsAuthenticated`, maka browser perlu session/auth yang valid atau Anda bisa memindahkan ke mode `AllowAny` untuk demo murni lokal.

> Untuk kebutuhan produksi, sebaiknya dibangun dengan framework frontend modern (React/Vue/Next.js) dan komponen chart yang lebih baik (Chart.js, Recharts, dsb.) serta autentikasi yang benar.

---

## 8. Ringkasan Alur Sistem

```
ingest_api / ingest_local / ingest_mysql
        │  (dedup + versioning otomatis)
        ▼
   raw_documents (Postgres/Supabase)
        │
   process_chunks
        │  (chunking -> embedding -> simpan vector)
        ▼
   document_chunks (pgvector)
        │
   POST /api/query/
        │  (embed pertanyaan -> similarity search -> prompt anti-halusinasi -> LLM Groq)
        ▼
   { answer, sources }  →  ditampilkan di chatbox

   GET /api/stats/  →  agregasi raw_documents  →  ditampilkan sebagai grafik dashboard
```

---

## 9. Catatan Keamanan & Produksi

- **Kontrol akses**: field `access_level` (`public` / `internal` / `restricted`) pada `RawDocument` membatasi data apa yang boleh dijawab ke user biasa vs. user staff. Untuk produksi, sambungkan ke sistem role/permission Django yang sesungguhnya, bukan hanya `is_staff`.
- **Data sensitif ke LLM eksternal**: Groq adalah API pihak ketiga. Pertimbangkan kebijakan data sebelum mengirim konten dari sumber sensitif (misal SIMPEG) ke LLM eksternal — bisa ditambahkan masking/redaction sebelum prompt dikirim.
- **REST_FRAMEWORK permission**: saat ini `AllowAny` di `settings.py` untuk memudahkan development. Ubah ke `IsAuthenticated` atau skema permission yang sesuai sebelum deploy.
- **`DEBUG=True`** di `.env` hanya untuk development — pastikan `DJANGO_DEBUG=False` dan `ALLOWED_HOSTS` diisi domain yang benar saat produksi.
- **Migrasi model embedding**: jika suatu saat mengganti `EMBEDDING_PROVIDER`, jalankan ulang `process_chunks` — pipeline akan otomatis mendeteksi chunk dengan `embedding_model` lama dan meng-generate ulang embedding-nya.

---

## 10. Troubleshooting Singkat

| Masalah | Kemungkinan Penyebab | Solusi |
|---|---|---|
| `relation "vector" does not exist` saat migrate | Extension pgvector belum diaktifkan | Jalankan `create extension if not exists vector;` di Supabase SQL Editor |
| `ValueError: DATABASE_URL tidak valid` | Format `DATABASE_URL` salah | Pastikan formatnya persis `postgresql://user:pass@host:port/dbname` |
| Similarity search selalu kosong | `score_threshold` di `retriever.py` terlalu ketat, atau belum ada chunk ter-generate | Jalankan `process_chunks`, atau naikkan nilai `score_threshold` |
| Proses embedding lambat di awal | Model `bge-m3` sedang diunduh pertama kali | Tunggu sampai selesai, atau pakai `EMBEDDING_PROVIDER=external` |
| Error saat `ingest_mysql` | Kredensial `MYSQL_SOURCE_*` salah/kosong | Cek kembali isian di `.env` |
