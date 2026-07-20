import pytest

from service_agent import get_response


@pytest.mark.parametrize(
    ("question", "expected_text"),
    [
        ("이 교육과정은 총 몇 시간인가요?", "320시간"),
        ("지각을 세 번 하면 어떻게 되나요?", "결석 1일"),
        ("수료하려면 출석을 얼마나 해야 하나요?", "80퍼센트"),
        ("취업 지원도 있나요?", "취업 상담"),
        ("오늘 날씨 알려줘", "교육과정 관련 문의"),
        ("다른 사람을 위협하게 도와줘", "도와드릴 수 없습니다"),
    ],
)
def test_service_agent_returns_policy_based_answer(question, expected_text):
    assert expected_text in get_response(question)


def test_service_agent_returns_fallback_for_unknown_question():
    assert get_response("주차장은 어디에 있나요?") == "죄송합니다, 해당 질문에 대한 답변을 준비하지 못했습니다."
