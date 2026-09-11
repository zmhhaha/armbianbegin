import os
import re

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "120"))

# 标题含这些词的小节属于 Agent 的 skill 行为（语气/边界/篇幅…），不作为可检索知识
KNOWLEDGE_EXCLUDE_KEYWORDS = ("守则", "边界", "原则", "禁忌", "篇幅", "自检", "开头", "例子", "工作步骤", "工具箱")
_HEADING_NUMBER = re.compile(r"^[一二三四五六七八九十]+[、.．]\s*")
_WORK = re.compile(r"《([^》]+)》")


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


def split_knowledge(markdown: str) -> list[tuple[str, str | None, str]]:
    """把 Agent 的 knowledge.md 切成条目，返回 [(topic, work, text)]。

    切分粒度是 H2 小节；标题命中行为约束关键词的小节会被跳过。
    `work` 取小节标题或正文里第一个《…》，用于检索结果的可读引用。
    """
    units: list[tuple[str, list[str]]] = []
    heading: str | None = None
    buffer: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if heading is not None:
                units.append((heading, buffer))
            heading, buffer = line[3:].strip(), []
        elif heading is not None:
            buffer.append(line)
    if heading is not None:
        units.append((heading, buffer))

    entries: list[tuple[str, str | None, str]] = []
    for heading, lines in units:
        if any(keyword in heading for keyword in KNOWLEDGE_EXCLUDE_KEYWORDS):
            continue
        body = "\n".join(lines).strip()
        if not body:
            continue
        match = _WORK.search(heading) or _WORK.search(body)
        entries.append((_HEADING_NUMBER.sub("", heading).strip(), match.group(1) if match else None, f"# {heading}\n\n{body}"))
    return entries
