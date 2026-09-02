"""
Prompt builder anti-halusinasi: menggabungkan konteks hasil retrieval
dengan pertanyaan user, dengan instruksi ketat agar LLM tidak mengarang.
"""

SYSTEM_PROMPT = """Kamu adalah asisten yang menjawab HANYA berdasarkan konteks yang diberikan di bawah.
Aturan ketat:
1. Jika jawaban tidak ada di dalam konteks, katakan dengan jelas bahwa informasi tidak ditemukan. Jangan mengarang.
2. Jangan gunakan pengetahuan di luar konteks yang diberikan.
3. Setiap klaim dalam jawaban harus bisa ditelusuri ke salah satu sumber di konteks.
4. Jawab dalam Bahasa Indonesia, singkat dan jelas.
"""


def build_prompt(
    question: str,
    chunks: list[dict],
    context_title: str = "",
    context_data: str = "",
) -> list[dict]:
    context_parts = []
    if context_title:
        context_parts.append(f"=== FOKUS DIAGRAM/TABEL: {context_title} ===")
    if context_data:
        context_parts.append(f"DATA ANALISA KHUSUS:\n{context_data}")

    if not chunks:
        retrieval_text = "(Tidak ada konteks tambahan relevan ditemukan dari dokumen.)"
    else:
        retrieval_text = "\n\n".join(
            f"[Sumber {i + 1}: {c['source_name']} - {c['title']}]\n{c['content']}"
            for i, c in enumerate(chunks)
        )

    context_parts.append(f"DOKUMEN TERKAIT:\n{retrieval_text}")
    context_text = "\n\n".join(context_parts)

    user_content = f"""Konteks Analisis:
{context_text}

Pertanyaan Pengguna: {question}

Instruksi:
Jawablah pertanyaan secara spesifik dan mendalam berdasarkan diagram/tabel dan dokumen di atas. Jelaskan angka, tren, latar belakang kebijakan, maupun kendala yang relevan. Sertakan referensi sumber jika tersedia."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

