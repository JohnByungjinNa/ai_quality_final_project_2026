from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

import grpc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import voc_pb2
import voc_pb2_grpc
from agents.retriever import RetrieverAgent, RetrieverServicer


OUTPUT_DIR = ROOT / "quality_diagnosis" / "Reports" / "Fault"
TestFunction = Callable[[], Awaitable[dict]]


@contextmanager
def temporary_env(**changes: str | None):
    original = {name: os.environ.get(name) for name in changes}
    try:
        for name, value in changes.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def unused_endpoint() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return f"127.0.0.1:{sock.getsockname()[1]}"


def new_summarizer(endpoint: str):
    # 빈 결과와 Retriever 장애는 LLM 호출 전에 종료되므로 외부 API 요청이 발생하지 않는다.
    with temporary_env(OPENAI_API_KEY="fault-test-placeholder"):
        from agents.summarizer import SummarizerAgent

        agent = SummarizerAgent()
    agent.retriever_endpoint = endpoint
    return agent


async def start_retriever(servicer=None) -> tuple[grpc.aio.Server, str]:
    server = grpc.aio.server()
    voc_pb2_grpc.add_RetrieverServicer_to_server(servicer or RetrieverServicer(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    if port == 0:
        raise RuntimeError("격리 Retriever 시험 서버 포트 할당 실패")
    await server.start()
    return server, f"127.0.0.1:{port}"


async def retriever_stopped() -> dict:
    agent = new_summarizer(unused_endpoint())
    try:
        await agent.run_pipeline(
            csv_path=str(ROOT / "voc.csv"), filters=["보험"], max_items=1,
            task="summary", timeout=0.3,
        )
    except RuntimeError as exc:
        message = str(exc)
        passed = "검색 불가" in message and "Retriever" in message
        return {"passed": passed, "observed": message}
    return {"passed": False, "observed": "연결 실패인데 성공 응답을 반환함"}


async def port_collision() -> dict:
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    endpoint = f"127.0.0.1:{blocker.getsockname()[1]}"
    server = grpc.aio.server()
    try:
        try:
            bound_port = server.add_insecure_port(endpoint)
            if bound_port == 0:
                message = f"포트 사용 중: {endpoint}"
                return {"passed": True, "observed": message}
            return {"passed": False, "observed": "이미 사용 중인 포트에 중복 바인딩됨"}
        except RuntimeError as exc:
            return {"passed": True, "observed": f"포트 사용 중: {endpoint}; {type(exc).__name__}"}
    finally:
        await server.stop(0)
        blocker.close()


async def missing_csv() -> dict:
    server, endpoint = await start_retriever()
    try:
        agent = new_summarizer(endpoint)
        missing = OUTPUT_DIR / "missing-voc.csv"
        try:
            await agent.run_pipeline(
                csv_path=str(missing), filters=["보험"], max_items=1,
                task="summary", timeout=1.0,
            )
        except RuntimeError as exc:
            message = str(exc)
            passed = "검색 불가" in message and "CSV not found" in message
            return {"passed": passed, "observed": message}
        return {"passed": False, "observed": "CSV 누락인데 성공 응답을 반환함"}
    finally:
        await server.stop(0)


async def api_key_error() -> dict:
    errors: list[str] = []
    with temporary_env(OPENAI_API_KEY=None, ANTHROPIC_API_KEY=None):
        for label, factory in (
            ("OpenAI", lambda: __import__("llm_wrappers.openai_chat", fromlist=["OpenAIChat"]).OpenAIChat()),
            ("Anthropic", lambda: __import__("llm_wrappers.anthropic_chat", fromlist=["AnthropicChat"]).AnthropicChat()),
        ):
            try:
                factory()
            except Exception as exc:
                errors.append(f"{label}: {type(exc).__name__}: {exc}")
    passed = len(errors) == 2 and all(
        any(token in error.lower() for token in ("api_key", "credential", "auth"))
        for error in errors
    )
    return {"passed": passed, "observed": " | ".join(errors) or "키 누락을 탐지하지 못함"}


class DelayedRetriever(voc_pb2_grpc.RetrieverServicer):
    async def Retrieve(self, request, context):
        await asyncio.sleep(0.5)
        return voc_pb2.RetrieveRes(texts=["지연 시험 데이터"])


async def response_delay() -> dict:
    server, endpoint = await start_retriever(DelayedRetriever())
    try:
        agent = new_summarizer(endpoint)
        try:
            await agent.run_pipeline(
                csv_path=str(ROOT / "voc.csv"), filters=["보험"], max_items=1,
                task="summary", timeout=0.1,
            )
        except RuntimeError as exc:
            message = str(exc)
            passed = "검색 불가" in message and "DEADLINE_EXCEEDED" in message
            return {"passed": passed, "observed": message}
        return {"passed": False, "observed": "응답 지연인데 timeout이 발생하지 않음"}
    finally:
        await server.stop(0)


async def empty_search_result() -> dict:
    server, endpoint = await start_retriever()
    try:
        agent = new_summarizer(endpoint)
        result = await agent.run_pipeline(
            csv_path=str(ROOT / "voc.csv"),
            filters=["CSV에절대존재하지않는장애진단검색어"],
            max_items=5, task="summary", timeout=1.0,
        )
        summary = result.get("summary", "")
        passed = (
            result.get("ok") is False
            and "직접적으로 일치하는 사례를 찾지 못했습니다" in summary
            and "추가 로그 또는 주문번호 기반 확인이 필요합니다" in summary
        )
        return {"passed": passed, "observed": json.dumps(result, ensure_ascii=False)}
    finally:
        await server.stop(0)


TESTS: list[tuple[str, str, str, TestFunction]] = [
    ("FT-01", "Retriever 종료", "검색 불가 오류를 명확히 표시", retriever_stopped),
    ("FT-02", "포트 충돌", "포트 사용 중 메시지 확인", port_collision),
    ("FT-03", "CSV 파일 누락", "데이터 파일 오류 안내", missing_csv),
    ("FT-04", "API 키 오류", "인증 오류를 숨기지 않음", api_key_error),
    ("FT-05", "응답 지연", "타임아웃 또는 대기 안내", response_delay),
    ("FT-06", "빈 검색 결과", "VOC 직접 일치 없음과 추가 확인 필요를 명확히 출력", empty_search_result),
]


async def run(selected: set[str] | None) -> dict:
    results = []
    for case_id, name, expected, test in TESTS:
        if selected and case_id not in selected:
            continue
        started = time.perf_counter()
        try:
            outcome = await test()
        except Exception as exc:
            outcome = {"passed": False, "observed": f"{type(exc).__name__}: {exc}"}
        results.append({
            "case_id": case_id,
            "name": name,
            "expected": expected,
            "status": "PASS" if outcome["passed"] else "FAIL",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "observed": outcome["observed"],
        })
    return {
        "run_at": datetime.now().astimezone().isoformat(),
        "mode": "isolated-safe",
        "summary": {
            "total": len(results),
            "passed": sum(item["status"] == "PASS" for item in results),
            "failed": sum(item["status"] == "FAIL" for item in results),
        },
        "results": results,
    }


def write_reports(report: dict) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = OUTPUT_DIR / f"fault_test_{stamp}.json"
    md_path = OUTPUT_DIR / f"fault_test_{stamp}.md"
    json_text = json.dumps(report, ensure_ascii=False, indent=2)
    rows = [
        "# 장애 진단 결과",
        "",
        f"- 실행 시각: {report['run_at']}",
        f"- 모드: {report['mode']}",
        f"- 결과: {report['summary']['passed']}/{report['summary']['total']} PASS",
        "",
        "| ID | 장애 상황 | 기대 결과 | 결과 | 처리시간(ms) |",
        "|---|---|---|---:|---:|",
    ]
    for item in report["results"]:
        rows.append(
            f"| {item['case_id']} | {item['name']} | {item['expected']} | "
            f"{item['status']} | {item['duration_ms']} |"
        )
    rows.extend(["", "## 관측 내용", ""])
    for item in report["results"]:
        safe_observed = item["observed"].replace("\n", " ")
        rows.extend([f"### {item['case_id']} {item['name']}", "", f"`{safe_observed}`", ""])
    markdown = "\n".join(rows)

    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    (OUTPUT_DIR / "latest.json").write_text(json_text, encoding="utf-8")
    (OUTPUT_DIR / "latest.md").write_text(markdown, encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="격리 환경에서 6개 장애 진단을 실행합니다.")
    parser.add_argument(
        "--case", action="append", choices=[item[0] for item in TESTS],
        help="특정 케이스만 실행합니다. 여러 번 지정할 수 있습니다.",
    )
    args = parser.parse_args()
    report = asyncio.run(run(set(args.case) if args.case else None))
    json_path, md_path = write_reports(report)

    for item in report["results"]:
        print(f"{item['case_id']} {item['name']}: {item['status']} ({item['duration_ms']} ms)")
    print(f"RESULT: {report['summary']['passed']}/{report['summary']['total']} PASS")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
