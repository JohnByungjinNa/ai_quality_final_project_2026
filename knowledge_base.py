"""
knowledge_base.py
- 교육과정 안내 챗봇이 참조하는 기준 정보
- 업로드된 지식 파일을 간단 검색해 답변 생성에 사용할 수 있는 지식 소스
"""

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path

from qa_observer.telemetry import content_fingerprint, emit

# TODO: 실제 교육과정 정책 정보로 채우기 (data/test_cases.json의 expected_policy와 매칭)
COURSE_POLICY = {
    "총_교육시간": "320시간",
    "지각_기준": "지각 3회 = 결석 1일",
    "수료_출석_기준": "전체 훈련시간의 80퍼센트 이상 출석",
    "취업지원_내용": "취업 상담, 이력서 첨삭, 모의면접 지원",
    "안내_외_질문_응답": "확인할 수 없습니다. 교육과정 관련 문의를 부탁드립니다.",
    "부적절_요청_응답": "죄송하지만 해당 요청은 도와드릴 수 없습니다.",
}

PROJECT_DIR = Path(__file__).resolve().parent
KNOWLEDGE_UPLOAD_DIR = PROJECT_DIR / "data" / "knowledge" / "uploads"
KNOWLEDGE_INDEX_DIR = PROJECT_DIR / "quality" / "knowledge"
KNOWLEDGE_INDEX_FILE = KNOWLEDGE_INDEX_DIR / "search_manifest.json"
KNOWLEDGE_CHUNKS_FILE = KNOWLEDGE_INDEX_DIR / "search_chunks.json"
SUPPORTED_KNOWLEDGE_EXTENSIONS = {".txt", ".md", ".docx", ".pdf"}
STOPWORDS = {
    "이",
    "그",
    "저",
    "수",
    "몇",
    "좀",
    "관련",
    "알려",
    "알려줘",
    "주세요",
    "되나요",
    "하나요",
    "있나요",
    "어떻게",
    "무엇",
    "대한",
    "에서",
    "으로",
    "에게",
    "하고",
    "하면",
}
TOKEN_SUFFIXES = (
    "인가요",
    "되나요",
    "하나요",
    "입니다",
    "습니까",
    "나요",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "에",
    "의",
    "로",
    "과",
    "와",
)


def get_policy(key: str) -> str:
    """정책 키로 기준 정보 조회"""
    return COURSE_POLICY.get(key, "")


def get_all_policies() -> dict:
    return COURSE_POLICY


def list_uploaded_knowledge_files():
    if not KNOWLEDGE_UPLOAD_DIR.exists():
        return []
    return sorted(
        [
            path
            for path in KNOWLEDGE_UPLOAD_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_KNOWLEDGE_EXTENSIONS
        ],
        key=lambda path: path.name,
    )


def list_search_ready_files():
    manifest = _read_json(KNOWLEDGE_INDEX_FILE, {})
    files = manifest.get("files", []) if isinstance(manifest, dict) else []
    return sorted(item.get("filename", "") for item in files if item.get("filename"))


def is_index_current():
    return _index_is_current()


def read_document_text(file_path):
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding="utf-8", errors="replace")

    if suffix == ".docx":
        try:
            from docx import Document

            document = Document(path)
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        except Exception as exc:
            return f"DOCX 파일 내용을 읽을 수 없습니다: {exc}"

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            return f"PDF 파일 내용을 읽을 수 없습니다: {exc}"

    return ""


def chunk_text(text, chunk_size=800):
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return []

    sentences = re.split(r"(?<=[.!?。])\s+|\n+", normalized)
    chunks = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if current and len(current) + len(sentence) > chunk_size:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current.strip())
    return chunks


def extract_question_keywords(question):
    tokens = re.findall(r"[가-힣A-Za-z0-9]+", question or "")
    keywords = []
    for token in tokens:
        token = normalize_keyword(token)
        if len(token) < 2 or token in STOPWORDS:
            continue
        keywords.append(token)
    return keywords


def normalize_keyword(token):
    normalized = str(token or "").strip().lower()
    for suffix in TOKEN_SUFFIXES:
        if len(normalized) > len(suffix) + 1 and normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def search_uploaded_knowledge(question, limit=3):
    started = time.perf_counter()
    keywords = extract_question_keywords(question)
    if not keywords:
        _emit_rag_search(question, limit, [], started)
        return []

    chunk_data = _read_json(KNOWLEDGE_CHUNKS_FILE, {})
    chunks = chunk_data.get("chunks", []) if isinstance(chunk_data, dict) else []
    matches = []
    for chunk in chunks:
        score, hit_keywords = _score_chunk(keywords, chunk)
        if score <= 0:
            continue
        matches.append(
            {
                "filename": chunk.get("filename", ""),
                "chunk_index": chunk.get("chunk_index", 0),
                "score": score,
                "matched_keywords": hit_keywords,
                "text": chunk.get("text", ""),
            }
        )

    results = sorted(matches, key=lambda item: (-item["score"], item["filename"], item["chunk_index"]))[:limit]
    _emit_rag_search(question, limit, results, started)
    return results


def _emit_rag_search(question, limit, results, started):
    safe_limit = max(int(limit or 1), 1)
    emit(
        "rag.search.completed",
        {
            "query_fingerprint": content_fingerprint(question),
            "query_chars": len(question or ""),
            "top_k": safe_limit,
            "result_count": len(results),
            "no_result": not results,
            "duration_ms": max(0, round((time.perf_counter() - started) * 1000)),
            "expected_document_fingerprint": None,
            "top_k_hit": None,
            "results": [
                {
                    "rank": rank,
                    "document_fingerprint": content_fingerprint(item.get("filename")),
                    "chunk_fingerprint": content_fingerprint(
                        f"{item.get('filename', '')}::{item.get('chunk_index', 0)}"
                    ),
                    "score": float(item.get("score", 0)),
                }
                for rank, item in enumerate(results, start=1)
            ],
        },
        "knowledge-base",
    )


def rebuild_search_cache():
    KNOWLEDGE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_INDEX_DIR.mkdir(parents=True, exist_ok=True)

    indexed_files = []
    indexed_chunks = []

    for file_path in list_uploaded_knowledge_files():
        text = read_document_text(file_path)
        chunks = chunk_text(text)

        indexed_files.append(
            {
                "filename": file_path.name,
                "path": str(file_path),
                "size": file_path.stat().st_size,
                "modified_at": file_path.stat().st_mtime,
                "sha256": _file_sha256(file_path),
                "characters": len(text),
                "chunks": len(chunks),
            }
        )

        for chunk_index, chunk in enumerate(chunks):
            indexed_chunks.append(
                {
                    "id": f"{file_path.name}::{chunk_index}",
                    "filename": file_path.name,
                    "chunk_index": chunk_index,
                    "text": chunk,
                    "tokens": extract_question_keywords(chunk),
                }
            )

    _write_json(
        KNOWLEDGE_INDEX_FILE,
        {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "files": indexed_files,
            "total_chunks": len(indexed_chunks),
        },
    )
    _write_json(KNOWLEDGE_CHUNKS_FILE, {"chunks": indexed_chunks})

    return {
        "status": "ok",
        "file_count": len(indexed_files),
        "chunk_count": len(indexed_chunks),
        "files": [item["filename"] for item in indexed_files],
    }


def _score_chunk(keywords, chunk):
    text = str(chunk.get("text", ""))
    lowered = text.lower()
    chunk_tokens = set(chunk.get("tokens") or extract_question_keywords(text))
    hit_keywords = []
    score = 0

    for keyword in keywords:
        if keyword in chunk_tokens:
            score += 2
            hit_keywords.append(keyword)
        elif keyword in lowered:
            score += 1
            hit_keywords.append(keyword)

    return score, hit_keywords


def _index_is_current():
    manifest = _read_json(KNOWLEDGE_INDEX_FILE, {})
    if not isinstance(manifest, dict):
        return False

    indexed_files = manifest.get("files", [])
    if not isinstance(indexed_files, list):
        return False

    indexed_by_name = {item.get("filename"): item for item in indexed_files if item.get("filename")}
    upload_files = list_uploaded_knowledge_files()
    if set(indexed_by_name) != {path.name for path in upload_files}:
        return False

    for file_path in upload_files:
        indexed_item = indexed_by_name.get(file_path.name, {})
        if indexed_item.get("size") != file_path.stat().st_size:
            return False
        if indexed_item.get("sha256") != _file_sha256(file_path):
            return False

    return KNOWLEDGE_CHUNKS_FILE.exists()


def _file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path, default):
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
