import io
import json
import logging
import re
import uuid
from pathlib import Path
from PIL import Image
from django.conf import settings

logger = logging.getLogger(__name__)


def get_figures_dir() -> Path:
    figures_dir = Path(settings.MEDIA_ROOT) / "extracted_figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    return figures_dir


def _clean_cell(val) -> str:
    """Membersihkan whitespace dan newline dalam cell tabel."""
    if val is None:
        return ""
    return re.sub(r"\s+", " ", str(val)).strip()


def _parse_num(val_str) -> float | None:
    """Mendeteksi dan mengonversi format numerik (Rupiah, persen, desimal, pemisah ribuan)."""
    if not val_str:
        return None
    cleaned = re.sub(r"[^\d,\.\-]", "", str(val_str)).strip()
    if not cleaned or cleaned in ("-", "--", "."):
        return None

    # Format campuran (misal 1.234.567,89 vs 1,234,567.89)
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "." in cleaned:
        parts = cleaned.split(".")
        is_year = len(parts) == 2 and parts[0].isdigit() and (1900 <= int(parts[0]) <= 2100)
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and not is_year):
            cleaned = cleaned.replace(".", "")

    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _classify_category(title: str, text_snippet: str = "") -> str:
    """Klasifikasi kategori secara generik berdasarkan kata kunci umum."""
    combined = f"{title} {text_snippet}".lower()
    if any(k in combined for k in ["gaji", "tunjangan", "honor", "kompensasi", "rupiah", "biaya", "anggaran", "apbn", "apbd", "dana", "pagu", "rp"]):
        return "Anggaran & Kompensasi"
    if any(k in combined for k in ["kinerja", "capaian", "sakip", "evaluasi", "indikator", "target", "realisasi", "ikp", "ikss", "ikro"]):
        return "Kinerja & Realisasi"
    if any(k in combined for k in ["peraturan", "regulasi", "undang", "uu", "perpres", "permen", "hukum", "pasal", "kebijakan"]):
        return "Regulasi & Kebijakan"
    if any(k in combined for k in ["struktur", "organisasi", "kelembagaan", "pohon", "tata kelola", "eselon", "biro"]):
        return "Struktur & Kelembagaan"
    if any(k in combined for k in ["diagram", "alur", "skema", "kerangka", "bagan", "peta", "tahapan", "arsitektur"]):
        return "Diagram & Kerangka Kerja"
    if any(k in combined for k in ["peduli", "pelayanan", "publik", "masyarakat", "layanan", "p2ham"]):
        return "Pelayanan Publik"
    return "Data & Statistik"


def _compute_table_key_stats(columns: list[str], rows: list[list]) -> dict:
    """Menghitung statistik ringkasan (tertinggi, terendah, rata-rata, tren) secara dinamis."""
    if not rows or not columns:
        return {
            "highest": "-",
            "lowest": "-",
            "average": "-",
            "trend": "Tidak ada data",
        }

    numeric_col_indices = []
    col_numeric_values = {}

    for c_idx in range(len(columns)):
        values = []
        is_curr = False
        is_pct = False
        for r in rows:
            if c_idx < len(r):
                raw_cell = str(r[c_idx] or "")
                if "Rp" in raw_cell or "rp" in raw_cell:
                    is_curr = True
                if "%" in raw_cell:
                    is_pct = True
                n = _parse_num(raw_cell)
                if n is not None:
                    label = str(r[0] if len(r) > 0 else "").strip()
                    values.append((n, label))

        if len(values) >= max(2, int(len(rows) * 0.35)):
            numeric_col_indices.append(c_idx)
            col_numeric_values[c_idx] = (values, is_curr, is_pct)

    if not numeric_col_indices:
        return {
            "highest": f"{len(rows)} Baris",
            "lowest": f"{len(columns)} Kolom",
            "average": "-",
            "trend": f"{len(rows)} entri terdata",
        }

    # Prioritaskan kolom mata uang (Rp), persentase (%), atau kolom metrik dengan magnitude terbesar
    curr_cols = [c for c in numeric_col_indices if col_numeric_values[c][1]]
    pct_cols = [c for c in numeric_col_indices if col_numeric_values[c][2]]

    if curr_cols:
        best_c_idx = curr_cols[0]
    elif pct_cols:
        best_c_idx = pct_cols[0]
    else:
        # Abaikan kolom nomor urut/ID dan pilih kolom dengan nilai tertinggi
        non_id_cols = [
            c for c in numeric_col_indices
            if columns[c].lower().strip() not in ("no", "no.", "nomor", "num", "id", "kode")
        ]
        if non_id_cols:
            best_c_idx = max(non_id_cols, key=lambda c: max(v[0] for v in col_numeric_values[c][0]))
        else:
            best_c_idx = numeric_col_indices[-1]

    values_data, is_curr, is_pct = col_numeric_values[best_c_idx]
    nums = [v[0] for v in values_data]
    if not nums:
        return {
            "highest": f"{len(rows)} Baris",
            "lowest": f"{len(columns)} Kolom",
            "average": "-",
            "trend": f"{len(rows)} entri terdata",
        }

    max_idx = nums.index(max(nums))
    min_idx = nums.index(min(nums))
    max_val = nums[max_idx]
    min_val = nums[min_idx]
    avg_val = sum(nums) / len(nums)

    max_label = str(values_data[max_idx][1]).strip()
    min_label = str(values_data[min_idx][1]).strip()

    def fmt_val(val: float) -> str:
        if is_curr:
            if val >= 1_000_000_000:
                return f"Rp {val/1_000_000_000:,.2f} Miliar".replace(",", "X").replace(".", ",").replace("X", ".")
            elif val >= 1_000_000:
                return f"Rp {val:,.0f}".replace(",", ".")
            else:
                return f"Rp {val:,.0f}".replace(",", ".")
        elif is_pct:
            return f"{val:g}%"
        else:
            if val == int(val):
                return f"{int(val):,}".replace(",", ".")
            return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    highest_str = fmt_val(max_val)
    if max_label and max_label != highest_str and not re.match(r"^\d+\.?$", max_label):
        highest_str += f" ({max_label})"

    lowest_str = fmt_val(min_val)
    if min_label and min_label != lowest_str and not re.match(r"^\d+\.?$", min_label):
        lowest_str += f" ({min_label})"

    avg_str = fmt_val(avg_val)

    if len(nums) >= 3:
        if nums[-1] > nums[0] * 1.05:
            trend = "Tren Meningkat"
        elif nums[-1] < nums[0] * 0.95:
            trend = "Tren Menurun"
        else:
            trend = "Tren Stabil / Fluktuatif"
    else:
        trend = f"{len(rows)} Baris Data"

    return {
        "highest": highest_str,
        "lowest": lowest_str,
        "average": avg_str,
        "trend": trend,
    }


def _generate_llm_analysis(
    title: str,
    context_type: str,
    data_summary: str,
    doc_title: str = "",
    fallback_analysis: str = "",
    fallback_insights: list[str] | None = None,
    fallback_questions: list[str] | None = None,
) -> tuple[str, list[str], list[str]]:
    """Memanggil LLM secara dinamis untuk analisis, wawasan, dan pertanyaan dengan fallback generik netral."""
    fallback_insights = fallback_insights or [
        f"Data terstruktur diekstrak secara otomatis dari dokumen {doc_title or 'terkait'}.",
        f"Memuat parameter dan rincian mengenai {title}.",
    ]
    fallback_questions = fallback_questions or [
        f"Apa simpulan utama dari {title}?",
        "Bagaimana rincian perbandingan data pada bagian ini?",
    ]
    if not fallback_analysis:
        fallback_analysis = f"Data {context_type} yang memuat ringkasan informasi dan parameter dari dokumen {doc_title or 'terkait'}."

    if not getattr(settings, "GROQ_API_KEY", None):
        return fallback_analysis, fallback_insights, fallback_questions

    prompt = f"""Anda adalah asisten analis dokumen profesional. Analisis {context_type} berikut dari dokumen "{doc_title or 'Dokumen'}":
Judul: {title}
Data:
{data_summary}

Berikan output dalam format JSON valid PERSIS seperti ini:
{{
  "analysis": "1-2 kalimat ringkasan analitis yang tajam dan faktual tentang data ini.",
  "insights": [
    "Poin temuan kunci 1",
    "Poin temuan kunci 2",
    "Poin temuan kunci 3"
  ],
  "suggested_questions": [
    "Pertanyaan relevan 1?",
    "Pertanyaan relevan 2?",
    "Pertanyaan relevan 3?"
  ]
}}
Hanya kembalikan objek JSON tanpa formatting markdown di luar JSON."""

    try:
        from query.services.llm_client import generate_answer

        messages = [
            {"role": "system", "content": "Anda adalah asisten ekstraksi data analitik. Selalu berikan output dalam format JSON valid."},
            {"role": "user", "content": prompt},
        ]
        raw_resp = generate_answer(messages)
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_resp.strip(), flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        parsed = json.loads(cleaned)

        analysis = str(parsed.get("analysis", "")).strip() or fallback_analysis
        insights = [str(x).strip() for x in parsed.get("insights", []) if str(x).strip()] or fallback_insights
        questions = [str(x).strip() for x in parsed.get("suggested_questions", []) if str(x).strip()] or fallback_questions
        return analysis, insights, questions
    except Exception as exc:
        logger.debug("LLM analysis generation fallback for %s: %s", title, exc)
        return fallback_analysis, fallback_insights, fallback_questions


def extract_pdf_figures(pdf_path_or_bytes, doc_id: str = "", doc_title: str = "", use_llm: bool = True) -> list[dict]:
    """
    Ekstraksi seluruh gambar, grafik, diagram, dan bagan asli dari PDF
    dengan klasifikasi kategori generik dan analisis berbasis konteks dokumen nyata.
    """
    from pypdf import PdfReader

    figures = []
    figures_dir = get_figures_dir()

    try:
        if isinstance(pdf_path_or_bytes, (str, Path)):
            reader = PdfReader(str(pdf_path_or_bytes))
            file_stem = Path(pdf_path_or_bytes).stem
        else:
            if hasattr(pdf_path_or_bytes, "seek"):
                pdf_path_or_bytes.seek(0)
            reader = PdfReader(pdf_path_or_bytes)
            file_stem = re.sub(r"[^\w\-]", "_", doc_title or doc_id or "doc")

        for page_idx, page in enumerate(reader.pages):
            page_num = page_idx + 1
            text = page.extract_text() or ""

            # Cari caption gambar/grafik/diagram di halaman ini
            captions = re.findall(
                r"((?:Gambar|Grafik|Diagram|Bagan|Pohon|Kerangka|Skema|Arsitektur)\s+[\d\.\-]+[^\n\r]+)",
                text,
                re.IGNORECASE,
            )

            # Jika tidak ada caption dengan pola nomor, cari baris heading
            if not captions:
                for line in text.splitlines():
                    cleaned_line = line.strip()
                    if re.match(r"^(Gambar|Grafik|Diagram|Bagan|Pohon Kinerja|Kerangka|Skema|Struktur)", cleaned_line, re.I):
                        if len(cleaned_line) > 5 and len(cleaned_line) < 120:
                            captions.append(cleaned_line)

            page_images = getattr(page, "images", [])
            for img_idx, img in enumerate(page_images):
                try:
                    img_data = img.data
                    im = Image.open(io.BytesIO(img_data))

                    # Abaikan icon kecil atau ornamen dekoratif
                    if im.width < 100 or im.height < 100:
                        continue

                    # Konversi mode warna agar kompatibel web (RGB / RGBA)
                    if im.mode not in ("RGB", "RGBA"):
                        im = im.convert("RGB")

                    safe_title_slug = re.sub(r"[^\w\-]", "_", file_stem)[:30]
                    ext = "png" if im.mode == "RGBA" or "png" in img.name.lower() else "jpg"
                    img_filename = f"{safe_title_slug}_p{page_num}_{img_idx}_{uuid.uuid4().hex[:6]}.{ext}"
                    out_path = figures_dir / img_filename

                    if ext == "png":
                        im.save(str(out_path), "PNG", optimize=True)
                    else:
                        im.save(str(out_path), "JPEG", quality=92)

                    caption = (
                        captions[img_idx].strip()
                        if img_idx < len(captions)
                        else (captions[0].strip() if captions else f"Gambar Halaman {page_num}")
                    )
                    caption = re.sub(r"\s+", " ", caption).strip()

                    category = _classify_category(caption, text[:300])

                    fallback_analysis = f"Bagan visual asli pada halaman {page_num} yang menyajikan data dan ilustrasi dalam dokumen {doc_title or file_stem}."
                    fallback_insights = [
                        f"Gambar bersumber dari halaman {page_num} dokumen {doc_title or file_stem}.",
                        f"Menyajikan representasi visual terkait {caption}.",
                    ]
                    fallback_questions = [
                        f"Apa penjelasan utama dari gambar {caption}?",
                        f"Bagaimana hubungan visual ini dengan topik bahasan pada halaman {page_num}?",
                    ]

                    if use_llm and len(figures) < 10:
                        analysis, insights, suggested_questions = _generate_llm_analysis(
                            title=caption,
                            context_type="gambar diagram / visual",
                            data_summary=f"Caption: {caption}\nHalaman: {page_num}\nKonteks Teks:\n{text[:500]}",
                            doc_title=doc_title or file_stem,
                            fallback_analysis=fallback_analysis,
                            fallback_insights=fallback_insights,
                            fallback_questions=fallback_questions,
                        )
                    else:
                        analysis, insights, suggested_questions = fallback_analysis, fallback_insights, fallback_questions

                    figures.append({
                        "id": f"{safe_title_slug}_p{page_num}_{img_idx}",
                        "title": caption,
                        "caption": caption,
                        "page": page_num,
                        "category": category,
                        "width": im.width,
                        "height": im.height,
                        "image_url": f"{settings.MEDIA_URL}extracted_figures/{img_filename}",
                        "doc_title": doc_title or file_stem,
                        "doc_id": doc_id,
                        "analysis": analysis,
                        "insights": insights,
                        "suggested_questions": suggested_questions,
                    })
                except Exception as exc:
                    logger.warning("Gagal ekstraksi gambar %s pada halaman %d: %s", getattr(img, "name", "unknown"), page_num, exc)

    except Exception as exc:
        logger.exception("Gagal membaca gambar dari PDF %s: %s", doc_title, exc)

    return figures


def _is_valid_grid_table(rows: list[list[str]]) -> bool:
    """Memeriksa apakah tabel hasil ekstraksi merupakan grid tabel yang valid (bukan teks paragraf terpotong)."""
    if not rows or len(rows) < 2:
        return False
    valid_row_count = 0
    for r in rows:
        non_empty = [c for c in r if c and str(c).strip()]
        if len(non_empty) >= 2:
            valid_row_count += 1
    return (valid_row_count / len(rows)) >= 0.5 and valid_row_count >= 2


def extract_pdf_tables(pdf_path_or_bytes, doc_id: str = "", doc_title: str = "", use_llm: bool = True) -> list[dict]:
    """
    Mengekstrak seluruh tabel terstruktur secara dinamis dari file PDF menggunakan pdfplumber.
    """
    import pdfplumber

    tables = []
    doc_label = doc_title or doc_id or "Dokumen"

    try:
        if isinstance(pdf_path_or_bytes, (str, Path)):
            pdf_ctx = pdfplumber.open(str(pdf_path_or_bytes))
        else:
            if hasattr(pdf_path_or_bytes, "seek"):
                pdf_path_or_bytes.seek(0)
            pdf_ctx = pdfplumber.open(pdf_path_or_bytes)

        with pdf_ctx as pdf:
            table_counter = 0
            for page_idx, page in enumerate(pdf.pages):
                page_num = page_idx + 1
                page_text = page.extract_text() or ""
                raw_tables = page.extract_tables() or []

                # Cari caption tabel di teks halaman
                page_table_captions = re.findall(
                    r"((?:Tabel|Table)\s+[\d\.\-]+[^\n\r]+)",
                    page_text,
                    re.IGNORECASE,
                )

                for t_idx, raw_tbl in enumerate(raw_tables):
                    if not raw_tbl or len(raw_tbl) < 2:
                        continue

                    # Bersihkan setiap cell
                    cleaned_grid = []
                    for r in raw_tbl:
                        if not r:
                            continue
                        cleaned_row = [_clean_cell(c) for c in r]
                        if any(c != "" for c in cleaned_row):
                            cleaned_grid.append(cleaned_row)

                    if not _is_valid_grid_table(cleaned_grid):
                        continue

                    # Normalisasi panjang kolom tiap baris
                    max_cols = max(len(r) for r in cleaned_grid)
                    for r in cleaned_grid:
                        while len(r) < max_cols:
                            r.append("")

                    # Pisahkan header dan data rows
                    raw_headers = cleaned_grid[0]
                    data_rows = cleaned_grid[1:]

                    # Jika baris pertama kosong sebagian besar, cari baris berikutnya sebagai header
                    if sum(1 for h in raw_headers if h) < 2 and len(data_rows) >= 2:
                        raw_headers = data_rows[0]
                        data_rows = data_rows[1:]

                    # Bersihkan header
                    headers = []
                    seen_headers = {}
                    for col_i, h in enumerate(raw_headers):
                        h_clean = h.strip() if h else f"Kolom {col_i + 1}"
                        if h_clean in seen_headers:
                            seen_headers[h_clean] += 1
                            h_clean = f"{h_clean} ({seen_headers[h_clean]})"
                        else:
                            seen_headers[h_clean] = 1
                        headers.append(h_clean)

                    if not data_rows:
                        continue

                    table_counter += 1

                    # Tentukan judul tabel
                    if t_idx < len(page_table_captions):
                        title = page_table_captions[t_idx].strip()
                    elif page_table_captions:
                        title = f"{page_table_captions[0].strip()} (Bagian {t_idx + 1})"
                    else:
                        title = f"Tabel {table_counter} - {doc_label} (Halaman {page_num})"

                    category = _classify_category(title, " ".join(headers))
                    key_stats = _compute_table_key_stats(headers, data_rows)

                    sample_rows_summary = "\n".join([f"Baris {i+1}: {', '.join(str(c) for c in r)}" for i, r in enumerate(data_rows[:6])])
                    data_summary = f"Kolom: {', '.join(headers)}\nTotal Baris: {len(data_rows)}\nContoh Data:\n{sample_rows_summary}"

                    fallback_analysis = f"Tabel data terstruktur dari dokumen {doc_label} memuat {len(data_rows)} baris data dan {len(headers)} kolom."
                    fallback_insights = [
                        f"Tabel bersumber dari halaman {page_num} dokumen {doc_label}.",
                        f"Memuat {len(data_rows)} baris entri data terstruktur.",
                    ]
                    fallback_questions = [
                        f"Apa rincian data pada {title}?",
                        "Bagaimana perbandingan nilai antar baris pada tabel ini?",
                    ]

                    if use_llm and table_counter <= 10:
                        analysis, insights, suggested_questions = _generate_llm_analysis(
                            title=title,
                            context_type="tabel data terstruktur",
                            data_summary=data_summary,
                            doc_title=doc_label,
                            fallback_analysis=fallback_analysis,
                            fallback_insights=fallback_insights,
                            fallback_questions=fallback_questions,
                        )
                    else:
                        analysis, insights, suggested_questions = fallback_analysis, fallback_insights, fallback_questions

                    tables.append({
                        "id": f"table_{table_counter}_{uuid.uuid4().hex[:6]}",
                        "title": title,
                        "source": doc_label,
                        "category": category,
                        "columns": headers,
                        "rows": data_rows,
                        "total_rows": len(data_rows),
                        "page": page_num,
                        "key_stats": key_stats,
                        "analysis": analysis,
                        "insights": insights,
                        "suggested_questions": suggested_questions,
                    })

    except Exception as exc:
        logger.exception("Gagal mengekstrak tabel dari PDF %s: %s", doc_title, exc)

    return tables


def extract_text_tables(raw_text: str, doc_id: str = "", doc_title: str = "", use_llm: bool = True) -> list[dict]:
    """
    Fallback parser untuk mengekstrak tabel Markdown / baris berstruktur tabular dari teks mentah.
    """
    tables = []
    doc_label = doc_title or doc_id or "Dokumen"
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    # Deteksi blok tabel markdown atau tabular berpola
    current_block = []
    table_blocks = []

    for line in lines:
        if "|" in line:
            current_block.append(line)
        else:
            # Cari baris yang memuat format angka berkolom (misal: "2020 81 77 4")
            parts = re.split(r"\s+", line)
            if len(parts) >= 3 and any(_parse_num(p) is not None for p in parts[1:]):
                current_block.append(line)
            else:
                if len(current_block) >= 2:
                    table_blocks.append(current_block)
                current_block = []

    if len(current_block) >= 2:
        table_blocks.append(current_block)

    for b_idx, block in enumerate(table_blocks):
        parsed_rows = []
        for line in block:
            if "|" in line:
                cells = [_clean_cell(c) for c in line.split("|")]
                cells = [c for c in cells if c != ""]
            else:
                cells = [_clean_cell(c) for c in re.split(r"\s+", line) if _clean_cell(c) != ""]

            # Abaikan separator markdown seperti |---|---|
            if cells and all(re.match(r"^:?-+:?$", c) for c in cells):
                continue
            if cells:
                parsed_rows.append(cells)

        if not _is_valid_grid_table(parsed_rows):
            continue

        max_cols = max(len(r) for r in parsed_rows)
        for r in parsed_rows:
            while len(r) < max_cols:
                r.append("")

        headers = [h or f"Kolom {i+1}" for i, h in enumerate(parsed_rows[0])]
        data_rows = parsed_rows[1:]

        if not data_rows:
            continue

        title = f"Tabel {b_idx + 1} - {doc_label}"
        category = _classify_category(title, " ".join(headers))
        key_stats = _compute_table_key_stats(headers, data_rows)

        sample_rows_summary = "\n".join([f"Baris {i+1}: {', '.join(str(c) for c in r)}" for i, r in enumerate(data_rows[:6])])
        data_summary = f"Kolom: {', '.join(headers)}\nTotal Baris: {len(data_rows)}\nContoh Data:\n{sample_rows_summary}"

        fallback_analysis = f"Tabel data terstruktur dari dokumen {doc_label} memuat {len(data_rows)} baris data dan {len(headers)} kolom."
        fallback_insights = [
            f"Tabel data teks dari dokumen {doc_label}.",
            f"Terdiri dari {len(data_rows)} entri baris data.",
        ]
        fallback_questions = [
            f"Apa simpulan data dari {title}?",
            "Bagaimana rincian perbandingan data pada tabel ini?",
        ]

        if use_llm and b_idx < 5:
            analysis, insights, suggested_questions = _generate_llm_analysis(
                title=title,
                context_type="tabel data",
                data_summary=data_summary,
                doc_title=doc_label,
                fallback_analysis=fallback_analysis,
                fallback_insights=fallback_insights,
                fallback_questions=fallback_questions,
            )
        else:
            analysis, insights, suggested_questions = fallback_analysis, fallback_insights, fallback_questions

        tables.append({
            "id": f"table_{b_idx + 1}_{uuid.uuid4().hex[:6]}",
            "title": title,
            "source": doc_label,
            "category": category,
            "columns": headers,
            "rows": data_rows,
            "total_rows": len(data_rows),
            "key_stats": key_stats,
            "analysis": analysis,
            "insights": insights,
            "suggested_questions": suggested_questions,
        })

    return tables


def extract_adaptive_tables(source_input, doc_id: str = "", doc_title: str = "", use_llm: bool = True) -> list[dict]:
    """
    Fungsi antarmuka utama ekstraksi tabel adaptif.
    Menerima path file PDF, file bytes, atau string teks, dan menghasilkan skema JSON tabel standar.
    """
    if isinstance(source_input, (Path, io.BytesIO, bytes)):
        return extract_pdf_tables(source_input, doc_id=doc_id, doc_title=doc_title, use_llm=use_llm)

    if isinstance(source_input, str):
        if "\n" not in source_input and len(source_input) < 300 and Path(source_input).exists() and Path(source_input).suffix.lower() == ".pdf":
            return extract_pdf_tables(source_input, doc_id=doc_id, doc_title=doc_title, use_llm=use_llm)
        return extract_text_tables(source_input, doc_id=doc_id, doc_title=doc_title, use_llm=use_llm)

    return []


def extract_adaptive_charts(source_input, doc_id: str = "", doc_title: str = "", tables: list[dict] | None = None, use_llm: bool = True) -> list[dict]:
    """
    Mengekstrak data deret numerik / statistik dari tabel dokumen nyata untuk dijadikan
    konfigurasi Chart.js lengkap secara generik tanpa data palsu/hardcoded.
    """
    charts = []
    doc_label = doc_title or doc_id or "Dokumen"

    if tables is None:
        tables = extract_adaptive_tables(source_input, doc_id=doc_id, doc_title=doc_title, use_llm=use_llm)

    palette = [
        {"bg": "rgba(59, 130, 246, 0.85)", "border": "#2563eb"},
        {"bg": "rgba(16, 185, 129, 0.85)", "border": "#059669"},
        {"bg": "rgba(245, 158, 11, 0.85)", "border": "#d97706"},
        {"bg": "rgba(168, 85, 247, 0.85)", "border": "#9333ea"},
        {"bg": "rgba(244, 63, 94, 0.85)", "border": "#e11d48"},
    ]

    for tbl_idx, tbl in enumerate(tables):
        columns = tbl.get("columns", [])
        rows = tbl.get("rows", [])
        if not rows or len(rows) < 2 or len(rows) > 35 or len(columns) < 2:
            continue

        # Identifikasi kolom label dan kolom numerik
        label_col_idx = 0
        numeric_cols = []

        # Cari kolom numerik
        for c_idx in range(len(columns)):
            col_name = columns[c_idx].lower().strip()
            if c_idx == 0 and col_name in ("no", "no.", "nomor"):
                label_col_idx = 1 if len(columns) > 1 else 0
                continue

            num_count = 0
            for r in rows:
                if c_idx < len(r) and _parse_num(str(r[c_idx])) is not None:
                    num_count += 1

            if num_count >= max(2, int(len(rows) * 0.5)):
                numeric_cols.append(c_idx)

        # Filter kolom dataset numerik (kecualikan label_col_idx)
        dataset_numeric_cols = [c for c in numeric_cols if c != label_col_idx]
        if not dataset_numeric_cols:
            continue

        # Ekstrak labels
        labels = []
        for r in rows:
            lbl = str(r[label_col_idx] if label_col_idx < len(r) else "").strip()
            labels.append(lbl or f"Item {len(labels)+1}")

        # Tentukan tipe chart (line jika label berformat tahun / urutan waktu, bar jika kategori)
        is_time_series = all(re.match(r"^(?:19|20)\d{2}", lbl) for lbl in labels if lbl)
        chart_type = "line" if is_time_series else "bar"

        # Deteksi satuan unit
        unit = ""
        sample_cell = str(rows[0][dataset_numeric_cols[0]] if dataset_numeric_cols and len(rows[0]) > dataset_numeric_cols[0] else "")
        if "%" in sample_cell or "%" in tbl.get("title", ""):
            unit = "%"
        elif "rp" in sample_cell.lower() or "rupiah" in tbl.get("title", "").lower():
            unit = "Rupiah (Rp)"
        elif "juta" in tbl.get("title", "").lower():
            unit = "Juta Rp"

        datasets = []
        for d_i, num_c_idx in enumerate(dataset_numeric_cols[:4]):  # Batasi maksimal 4 dataset per chart
            c_name = columns[num_c_idx]
            col_data = []
            for r in rows:
                val = _parse_num(str(r[num_c_idx])) if num_c_idx < len(r) else None
                col_data.append(val if val is not None else 0)

            c_style = palette[d_i % len(palette)]
            ds = {
                "label": c_name,
                "data": col_data,
                "backgroundColor": c_style["bg"] if chart_type == "bar" else "rgba(59, 130, 246, 0.15)",
                "borderColor": c_style["border"],
                "borderWidth": 2 if chart_type == "line" else 1.5,
                "borderRadius": 6 if chart_type == "bar" else 0,
            }
            if chart_type == "line":
                ds["tension"] = 0.2
                ds["pointRadius"] = 5
                ds["fill"] = False
            datasets.append(ds)

        if not datasets:
            continue

        chart_id = f"chart_{tbl_idx}_{uuid.uuid4().hex[:6]}"
        chart_title = tbl.get("title", f"Grafik Data {tbl_idx + 1}")

        charts.append({
            "id": chart_id,
            "title": chart_title,
            "subtitle": f"Visualisasi Data - {doc_label}",
            "type": chart_type,
            "category": tbl.get("category", "Statistik & Kinerja"),
            "unit": unit,
            "doc_title": doc_label,
            "labels": labels,
            "key_stats": tbl.get("key_stats", {}),
            "analysis": tbl.get("analysis", f"Grafik visualisasi data berdasarkan {chart_title}."),
            "insights": tbl.get("insights", [f"Visualisasi data dari tabel {chart_title}."]),
            "suggested_questions": tbl.get("suggested_questions", [
                f"Bagaimana tren pada grafik {chart_title}?",
                "Apa nilai tertinggi dan terendah pada grafik ini?",
            ]),
            "datasets": datasets,
            "notes": f"Sumber: {tbl.get('source', doc_label)}",
        })

    return charts
