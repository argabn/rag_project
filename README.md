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

### Untuk Development Lokal
- Python 3.11+
- Akun **Supabase** (atau Postgres lain yang mendukung extension `pgvector`)
- Akun **Groq** untuk API key LLM
- (Opsional) Akses ke sumber API internal (e-office, SIMPEG, arsip digital), file lokal, dan/atau database MySQL yang ingin di-ingest

### Untuk Docker / Docker Compose
- **Docker** 20.10+ dan **Docker Compose** 2.0+ (untuk menjalankan semua service dalam container)
- Atau hanya **Docker** jika Anda menggunakan Supabase eksternal

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

Lalu edit `.env` dan isi minimal (untuk dev lokal):

```bash
# Ganti dengan URL database Supabase Anda
DATABASE_URL=postgresql://postgres:[PASSWORD]@[SUPABASE_HOST]:5432/postgres

# Ganti dengan API key Groq Anda (dari https://console.groq.com/)
GROQ_API_KEY=isi-dengan-api-key-groq-anda

# Django config
DJANGO_SECRET_KEY=ubah-dengan-secret-key-acak-panjang-minimal-50-char
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Embedding config (local)
EMBEDDING_PROVIDER=bge-m3
EMBEDDING_DIM=1024
```

Field lain (`EOFFICE_TOKEN`, `SIMPEG_TOKEN`, `ARSIP_TOKEN`, `MYSQL_SOURCE_*`) diisi sesuai sumber data yang ingin dipakai — boleh dikosongkan kalau sumber tersebut belum dipakai.

**Catatan**: Untuk Docker Compose, `.env` akan di-generate otomatis (lihat bagian 6.2 & 6.3).

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

## 6. Menjalankan Server & Deployment

### 6.1. Mode Development Lokal (Virtual Environment)

**Prasyarat**: Virtual environment sudah disetup dan `requirements.txt` sudah di-install (lihat bagian 3.1 & 3.2).

```bash
# Aktifkan virtual environment (jika belum aktif)
source venv/bin/activate          # Linux/macOS
# atau: venv\Scripts\activate     # Windows

# Jalankan server development
python manage.py runserver
```

Server berjalan di `http://localhost:8000`.

**Tips**:
- Server development auto-reload saat ada perubahan file
- Cocok untuk iterasi cepat saat development
- Jangan gunakan di production — gunakan Gunicorn/Docker (lihat 6.2)

### 6.2. Mode Docker (Image Lokal)

Jika Anda sudah punya database eksternal (Supabase), cukup jalankan Django dalam container:

```bash
# Build image Docker
docker build -t rag-project:latest .

# Jalankan container
docker run -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/dokumen:/app/dokumen \
  rag-project:latest
```

**Penjelasan flags**:
- `-p 8000:8000` — map port container ke host
- `--env-file .env` — load environment variables dari file `.env`
- `-v $(pwd)/dokumen:/app/dokumen` — mount folder lokal untuk ingestion file

Server berjalan di `http://localhost:8000`.

**Catatan**: Pastikan `DATABASE_URL` di `.env` menunjuk ke database yang valid (bukan `localhost` — gunakan Supabase atau PostgreSQL eksternal).

### 6.3. Mode Docker Compose (Recommended untuk Development)

Setup otomatis Django + PostgreSQL dalam container:

```bash
# Buat file docker-compose.yml di root project (lihat template di bawah)
# Kemudian jalankan:
docker-compose up --build
```

**Template `docker-compose.yml`**:

```yaml
version: '3.9'

services:
  postgres:
    image: pgvector/pgvector:pg16-latest
    container_name: rag-postgres
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: rag_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-pgvector.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  django:
    build: .
    container_name: rag-django
    command: sh -c "python manage.py migrate && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4"
    environment:
      DATABASE_URL: postgresql://postgres:postgres@postgres:5432/rag_db
      DJANGO_SECRET_KEY: dev-secret-key-change-in-production
      DJANGO_DEBUG: "False"
      DJANGO_ALLOWED_HOSTS: localhost,127.0.0.1,0.0.0.0
      GROQ_API_KEY: ${GROQ_API_KEY}
      EMBEDDING_PROVIDER: bge-m3
      EMBEDDING_DIM: "1024"
      CORS_ALLOWED_ORIGINS: http://localhost:8000,http://127.0.0.1:8000
    ports:
      - "8000:8000"
    volumes:
      - ./dokumen:/app/dokumen
      - ./logs:/app/logs
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/stats/"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  postgres_data:

networks:
  default:
    name: rag-network
```

**Buat file `init-pgvector.sql`** di root project untuk setup extension:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

**Jalankan**:

```bash
# Setup pertama kali (build + migrate)
docker-compose up --build

# Jalankan ulang (tanpa rebuild)
docker-compose up

# Stop containers
docker-compose down

# Stop + hapus data database
docker-compose down -v
```

Server berjalan di `http://localhost:8000`, PostgreSQL di `localhost:5432`.

**Keuntungan Docker Compose**:
- Setup database otomatis (tidak perlu Supabase)
- Cocok untuk development team (semua pakai environment yang sama)
- Mudah reset database (jalankan `docker-compose down -v`)

### 6.4. Endpoint yang tersedia

| Endpoint         | Method | Fungsi                                      |
|-------------------|--------|----------------------------------------------|
| `/api/query/`      | POST   | Chatbox — tanya jawab berbasis RAG           |
| `/api/stats/`      | GET    | Statistik/agregasi dokumen untuk grafik      |
| `/admin/`           | GET    | Django admin panel                           |

### 6.5. Contoh test lewat curl

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

## 9. Production Deployment Guide

### 9.1. Checklist Sebelum Deploy

```bash
# 1. Environment variables
- [ ] DJANGO_SECRET_KEY = string acak panjang (minimal 50 char)
- [ ] DJANGO_DEBUG = False
- [ ] DATABASE_URL = Postgres production (bukan lokal)
- [ ] GROQ_API_KEY = valid API key
- [ ] DJANGO_ALLOWED_HOSTS = domain production Anda
- [ ] CORS_ALLOWED_ORIGINS = domain frontend production
```

### 9.2. Deploy ke Server dengan Docker

```bash
# 1. Clone repository di server
git clone <repo-url> /home/app/rag_project
cd /home/app/rag_project

# 2. Buat .env dengan config production
cat > .env << EOF
DATABASE_URL=postgresql://user:pass@prod-db-host:5432/rag_db
DJANGO_SECRET_KEY=$(openssl rand -base64 50)
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
GROQ_API_KEY=xxxxx
EMBEDDING_PROVIDER=bge-m3
EMBEDDING_DIM=1024
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
EOF

# 3. Build dan push image ke registry (Docker Hub / ECR / GCR)
docker build -t your-registry/rag-project:latest .
docker push your-registry/rag-project:latest

# 4. Jalankan container di server production
docker run -d --name rag-prod \
  -p 80:8000 \
  --restart always \
  --env-file .env \
  -v /home/app/rag_project/dokumen:/app/dokumen \
  -v /home/app/rag_project/logs:/app/logs \
  your-registry/rag-project:latest

# 5. Setup Nginx reverse proxy (opsional, tapi recommended)
# (lihat template Nginx di bawah)
```

### 9.3. Template Nginx Reverse Proxy

Buat file `/etc/nginx/sites-available/rag-project`:

```nginx
upstream django_app {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    client_max_body_size 50M;

    location / {
        proxy_pass http://django_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/app/rag_project/staticfiles/;
    }
}
```

Lalu enable:

```bash
sudo ln -s /etc/nginx/sites-available/rag-project /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 9.4. Setup SSL dengan Let's Encrypt (Recommended)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Certbot otomatis update Nginx config untuk HTTPS.

### 9.5. Monitoring & Logging

```bash
# Lihat logs container
docker logs -f rag-prod

# Setup log rotation (di file `/app/logs/rag.log`)
# Add cron job untuk backup logs
0 0 * * * tar -czf /home/app/backups/logs-$(date +%Y%m%d).tar.gz /home/app/rag_project/logs/
```

---

## 10. Catatan Keamanan & Produksi

- **Kontrol akses**: field `access_level` (`public` / `internal` / `restricted`) pada `RawDocument` membatasi data apa yang boleh dijawab ke user biasa vs. user staff. Untuk produksi, sambungkan ke sistem role/permission Django yang sesungguhnya, bukan hanya `is_staff`.
- **Data sensitif ke LLM eksternal**: Groq adalah API pihak ketiga. Pertimbangkan kebijakan data sebelum mengirim konten dari sumber sensitif (misal SIMPEG) ke LLM eksternal — bisa ditambahkan masking/redaction sebelum prompt dikirim.
- **REST_FRAMEWORK permission**: saat ini `AllowAny` di `settings.py` untuk memudahkan development. Ubah ke `IsAuthenticated` atau skema permission yang sesuai sebelum deploy.
- **`DEBUG=True`** di `.env` hanya untuk development — pastikan `DJANGO_DEBUG=False` dan `ALLOWED_HOSTS` diisi domain yang benar saat produksi.
- **Migrasi model embedding**: jika suatu saat mengganti `EMBEDDING_PROVIDER`, jalankan ulang `process_chunks` — pipeline akan otomatis mendeteksi chunk dengan `embedding_model` lama dan meng-generate ulang embedding-nya.

---

## 11. Troubleshooting Singkat

| Masalah | Kemungkinan Penyebab | Solusi |
|---|---|---|
| `relation "vector" does not exist` saat migrate | Extension pgvector belum diaktifkan | **Supabase**: Jalankan `create extension if not exists vector;` di SQL Editor. **Docker Compose**: Extension sudah auto-enable via `init-pgvector.sql` |
| `ValueError: DATABASE_URL tidak valid` | Format `DATABASE_URL` salah | Pastikan formatnya persis `postgresql://user:pass@host:port/dbname`. Di Docker Compose: `postgresql://postgres:postgres@postgres:5432/rag_db` |
| `Connection refused` ke database saat Docker run | Container Django start sebelum PostgreSQL siap | Gunakan Docker Compose yang sudah punya `healthcheck` dan `depends_on`, atau tambahkan delay dengan `sleep 10` sebelum migrate |
| Similarity search selalu kosong | `score_threshold` di `retriever.py` terlalu ketat, atau belum ada chunk ter-generate | Jalankan `python manage.py process_chunks`, atau naikkan nilai `score_threshold` |
| Proses embedding lambat di awal | Model `bge-m3` sedang diunduh pertama kali (~2GB) | Tunggu sampai selesai, atau pakai `EMBEDDING_PROVIDER=external`. Di Docker Compose, mount volume untuk cache model |
| Error saat `ingest_mysql` | Kredensial `MYSQL_SOURCE_*` salah/kosong | Cek kembali isian di `.env`. MySQL server harus accessible dari container Django |
| Docker: `permission denied` saat mount volume | User dalam container tidak punya akses folder | Jalankan dengan `--user` flag atau ubah permission folder: `chmod 777 ./dokumen` |
| Docker Compose: `postgres_data volume already exists` | Conflict dengan data lama | Jalankan `docker-compose down -v` untuk reset, atau ubah nama volume di `docker-compose.yml` |
