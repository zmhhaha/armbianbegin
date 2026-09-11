import os

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "120"))

def split_chunks(text: str) -> list[str]:
    paragraphs = [part.strip() for part in text.replace("\r\n", "\n").split("\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        while len(paragraph) > CHUNK_SIZE:
            piece = paragraph[:CHUNK_SIZE]
            chunks.append((current + "\n" + piece).strip() if current else piece)
            current = piece[-CHUNK_OVERLAP:] if CHUNK_OVERLAP else ""
            paragraph = paragraph[CHUNK_SIZE - CHUNK_OVERLAP:] if CHUNK_OVERLAP else paragraph[CHUNK_SIZE:]
        candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        if current and len(candidate) > CHUNK_SIZE:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text.strip()]
