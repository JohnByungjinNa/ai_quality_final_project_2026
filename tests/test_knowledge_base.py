import json

import knowledge_base


def _patch_knowledge_paths(monkeypatch, tmp_path):
    upload_dir = tmp_path / "data" / "knowledge" / "uploads"
    index_dir = tmp_path / "quality" / "knowledge"
    upload_dir.mkdir(parents=True)

    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_INDEX_DIR", index_dir)
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_INDEX_FILE", index_dir / "search_manifest.json")
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_CHUNKS_FILE", index_dir / "search_chunks.json")

    return upload_dir, index_dir


def test_rebuild_search_cache_creates_searchable_local_index(tmp_path, monkeypatch):
    upload_dir, index_dir = _patch_knowledge_paths(monkeypatch, tmp_path)
    (upload_dir / "policy.txt").write_text(
        "교육시간은 총 320시간입니다.\n지각 3회는 결석 1일로 처리됩니다.",
        encoding="utf-8",
    )

    result = knowledge_base.rebuild_search_cache()

    assert result["file_count"] == 1
    assert result["chunk_count"] == 1
    assert knowledge_base.list_search_ready_files() == ["policy.txt"]
    assert knowledge_base.is_index_current() is True

    manifest = json.loads((index_dir / "search_manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"][0]["filename"] == "policy.txt"
    assert manifest["total_chunks"] == 1

    matches = knowledge_base.search_uploaded_knowledge("지각을 세 번 하면 어떻게 되나요?", limit=1)
    assert matches
    assert matches[0]["filename"] == "policy.txt"
    assert "결석 1일" in matches[0]["text"]


def test_search_uses_last_confirmed_index_until_rebuild(tmp_path, monkeypatch):
    upload_dir, _ = _patch_knowledge_paths(monkeypatch, tmp_path)
    policy_file = upload_dir / "policy.txt"
    policy_file.write_text("교육시간은 총 320시간입니다.", encoding="utf-8")

    knowledge_base.rebuild_search_cache()

    policy_file.write_text("취업 상담은 이력서 첨삭과 모의면접을 지원합니다.", encoding="utf-8")

    assert knowledge_base.is_index_current() is False
    assert knowledge_base.search_uploaded_knowledge("취업 상담 지원", limit=1) == []

    knowledge_base.rebuild_search_cache()
    matches = knowledge_base.search_uploaded_knowledge("취업 상담 지원", limit=1)

    assert matches
    assert "모의면접" in matches[0]["text"]
