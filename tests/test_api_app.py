from fastapi.testclient import TestClient

from api_app import app


client = TestClient(app)


def test_root_endpoint_lists_available_endpoints():
    response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["endpoints"]["health"] == "GET /health"
    assert body["endpoints"]["ask"] == "POST /ask"


def test_health_endpoint_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "service-agent"}


def test_post_ask_returns_answer():
    response = client.post("/ask", json={"question": "이 교육과정은 총 몇 시간인가요?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "이 교육과정은 총 320시간 과정입니다."


def test_get_ask_returns_answer():
    response = client.get("/ask", params={"question": "지각을 세 번 하면 어떻게 되나요?"})

    assert response.status_code == 200
    assert "결석 1일" in response.json()["answer"]


def test_post_ask_rejects_empty_question():
    response = client.post("/ask", json={"question": ""})

    assert response.status_code == 422


def test_get_ask_requires_question_parameter():
    response = client.get("/ask")

    assert response.status_code == 422


def test_ask_response_contains_original_question():
    question = "취업 지원도 있나요?"
    response = client.post("/ask", json={"question": question})

    assert response.status_code == 200
    assert response.json()["question"] == question
