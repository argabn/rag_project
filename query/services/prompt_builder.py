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


def build_prompt(question: str, chunks: list[dict]) -> list[dict]:
    if not chunks:
        context_text = "(Tidak ada konteks relevan ditemukan.)"
    else:
        context_text = "\n\n".join(
            f"[Sumber {i + 1}: {c['source_name']} - {c['title']}]\n{c['content']}"
            for i, c in enumerate(chunks)
        )

    user_content = f"""Konteks:
{context_text}

Pertanyaan: {question}

Jawab hanya berdasarkan konteks di atas. Sertakan referensi [Sumber N] yang relevan di akhir jawaban."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
