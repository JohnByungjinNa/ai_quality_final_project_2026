import importlib
import sys

from core.paths import RULE_KNOWLEDGE_UPLOAD_DIR, RULE_PROJECT_DIR, SUPPORTED_KNOWLEDGE_EXTENSIONS

def import_rule_knowledge_module():
    if not RULE_PROJECT_DIR.exists():
        raise FileNotFoundError(f"규칙 기반 프로젝트 폴더를 찾을 수 없습니다: {RULE_PROJECT_DIR}")

    rule_project_path = str(RULE_PROJECT_DIR)
    if rule_project_path not in sys.path:
        sys.path.insert(0, rule_project_path)

    module = importlib.import_module("knowledge_base")
    return importlib.reload(module)


def list_knowledge_upload_files():
    if not RULE_KNOWLEDGE_UPLOAD_DIR.exists():
        return []
    return sorted(
        [
            path
            for path in RULE_KNOWLEDGE_UPLOAD_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_KNOWLEDGE_EXTENSIONS
        ],
        key=lambda path: path.name,
    )


def get_indexed_knowledge_files():
    try:
        knowledge_base = import_rule_knowledge_module()
        list_ready = getattr(knowledge_base, "list_search_ready_files", None)
        if not list_ready:
            return set()
        return set(list_ready())
    except Exception:
        return set()


def is_knowledge_index_current():
    try:
        knowledge_base = import_rule_knowledge_module()
        is_current = getattr(knowledge_base, "is_index_current", None)
        if not is_current:
            return False
        return bool(is_current())
    except Exception:
        return False


def read_document_text(file_path):
    suffix = file_path.suffix.lower()
    if suffix in {".txt", ".md"}:
        for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
            try:
                return file_path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return file_path.read_text(encoding="utf-8", errors="replace")

    if suffix == ".docx":
        try:
            from docx import Document

            document = Document(file_path)
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        except Exception as exc:
            return f"DOCX 파일 내용을 읽을 수 없습니다: {exc}"

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(file_path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            try:
                from PyPDF2 import PdfReader

                reader = PdfReader(str(file_path))
                return "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as exc:
                return f"PDF 파일 내용을 읽을 수 없습니다: {exc}"

    return "지원하지 않는 파일 형식입니다."


def chunk_text(text, chunk_size=800):
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size) if text[index : index + chunk_size].strip()]


def read_knowledge_file_text(file_path):
    try:
        knowledge_base = import_rule_knowledge_module()
        read_text = getattr(knowledge_base, "read_document_text", None)
        if read_text:
            return read_text(file_path)
        return read_document_text(file_path)
    except Exception as exc:
        try:
            return read_document_text(file_path)
        except Exception:
            return f"파일 내용을 읽을 수 없습니다: {exc}"


def rebuild_knowledge_index():
    knowledge_base = import_rule_knowledge_module()
    rebuild = getattr(knowledge_base, "rebuild_search_cache", None)
    if not rebuild:
        raise RuntimeError("현재 knowledge_base.py에는 문서 검색 상태 확인 함수가 없습니다.")
    return rebuild()


def remove_knowledge_upload_file(filename):
    target_path = (RULE_KNOWLEDGE_UPLOAD_DIR / filename).resolve()
    upload_root = RULE_KNOWLEDGE_UPLOAD_DIR.resolve()
    if upload_root in target_path.parents and target_path.exists():
        target_path.unlink()


def status_color(status):
    return {
        "ok": "#16a34a",
        "changed": "#dc2626",
        "empty": "#94a3b8",
    }.get(status, "#94a3b8")


def status_icon_svg(icon_type, color):
    if icon_type == "database":
        return f"""
        <svg width="34" height="34" viewBox="0 0 34 34" fill="none" xmlns="http://www.w3.org/2000/svg">
          <ellipse cx="17" cy="8" rx="11" ry="5" fill="{color}" opacity="0.95"/>
          <path d="M6 8v9c0 2.8 4.9 5 11 5s11-2.2 11-5V8" stroke="{color}" stroke-width="3" fill="none"/>
          <path d="M6 17v8c0 2.8 4.9 5 11 5s11-2.2 11-5v-8" stroke="{color}" stroke-width="3" fill="none"/>
        </svg>
        """
    return f"""
    <svg width="34" height="34" viewBox="0 0 34 34" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 10c0-2.2 1.8-4 4-4h7l3 4h8c2.2 0 4 1.8 4 4v12c0 2.2-1.8 4-4 4H8c-2.2 0-4-1.8-4-4V10Z" fill="{color}" opacity="0.95"/>
      <path d="M4 14h26" stroke="white" stroke-opacity="0.75" stroke-width="2"/>
    </svg>
    """


