"""
Chunking service: memecah teks panjang jadi bagian-bagian kecil,
dengan overlap supaya konteks antar-chunk tidak putus total.
"""
import re


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    Chunking berbasis jumlah kata (word-based), sederhana tapi cukup
    predictable untuk kontrol token count di embedding model.

    chunk_size : jumlah kata per chunk
    overlap    : jumlah kata yang tumpang tindih antar chunk berurutan
    """
    text = clean_text(text)
    words = text.split(" ")

    if not words or words == [""]:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))

        if end >= len(words):
            break
        start = end - overlap  # mundur sedikit untuk overlap

    return chunks
