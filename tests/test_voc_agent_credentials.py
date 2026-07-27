import sys
from pathlib import Path

import grpc

from dashboard.services import voc_quality_service


RUNTIME_DIR = Path(__file__).resolve().parents[1] / "voc_quality_runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from utils.agent_errors import agent_rpc_error


def test_agent_rpc_error_maps_openai_401_without_key_fragment():
    status, message = agent_rpc_error(
        RuntimeError(
            "Error code: 401 - Incorrect API key provided: "
            "sk-proj-examplecredential123456789"
        ),
        "Summarizer.MakeCandidates",
    )

    assert status == grpc.StatusCode.UNAUTHENTICATED
    assert "OpenAI API 키 인증 실패" in message
    assert "sk-proj-" not in message
    assert "전체를 재시작" in message


def test_dashboard_rpc_error_maps_authentication_to_actionable_message():
    code, message = voc_quality_service._agent_rpc_error_details(
        "AioRpcError status=StatusCode.UNAUTHENTICATED "
        "details=Incorrect API key provided: sk-proj-examplecredential123456789"
    )

    assert code == "OPENAI_AUTH_FAILED"
    assert "HTTP 401" in message
    assert "OPENAI_API_KEY" in message
    assert "sk-proj-" not in message


def test_test_agent_rpc_does_not_return_raw_credential(monkeypatch):
    def raise_auth_error(_awaitable):
        _awaitable.close()
        raise RuntimeError(
            "401 Incorrect API key provided: sk-proj-examplecredential123456789"
        )

    monkeypatch.setattr(voc_quality_service.asyncio, "run", raise_auth_error)

    result = voc_quality_service.test_agent_rpc("Summarizer", 6103)

    assert result["ok"] is False
    assert result["error_code"] == "OPENAI_AUTH_FAILED"
    assert "sk-proj-" not in result["summary"]


def test_openai_credential_check_reports_missing_configuration(monkeypatch):
    monkeypatch.setattr(
        voc_quality_service,
        "_agent_env_value",
        lambda _name: ("", ""),
    )

    result = voc_quality_service.check_openai_agent_credential()

    assert result["ok"] is False
    assert result["status"] == "NOT_CONFIGURED"
    assert "설정되지 않았습니다" in result["message"]
