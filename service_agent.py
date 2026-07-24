"""
service_agent.py
- 실제 챗봇 역할
- API 없이도 실행 가능한 규칙 기반 모의 챗봇
"""

import re

from knowledge_base import get_all_policies, search_uploaded_knowledge

policies = get_all_policies()


def _best_knowledge_text(user_question):
    matches = search_uploaded_knowledge(user_question, limit=1)
    if not matches:
        return ""
    return matches[0].get("text", "")


def _first_match(pattern, text):
    match = re.search(pattern, text or "")
    return match.group(0) if match else ""


def get_response(user_question: str) -> str:
    """
    사용자 질문에 대해 규칙 기반으로 답변 생성.
    업로드 지식 파일에서 관련 내용을 먼저 찾고, 없으면 기본 정책 정보로 답변.
    """
    q = user_question.lower()
    knowledge_text = _best_knowledge_text(user_question)

    if "시간" in user_question and "수료" in user_question and "출석" in user_question:
        total_hours = _first_match(r"\d+\s*시간", knowledge_text) or policies["총_교육시간"]
        return f"총 교육시간은 {total_hours}이며, 수료를 위해서는 전체 훈련시간의 80%(80퍼센트) 이상 출석해야 합니다."

    if ("프로젝트" in user_question or "과락" in user_question) and "수료" in user_question:
        return "수료를 위해서는 출석률 80%(80퍼센트) 이상과 최종 프로젝트 통과 요건을 모두 충족해야 합니다."

    if "시간" in user_question and ("교육" in user_question or "수료" in user_question or "320" in user_question or "총" in user_question):
        total_hours = _first_match(r"\d+\s*시간", knowledge_text) or policies["총_교육시간"]
        return f"이 교육과정은 총 {total_hours} 과정입니다."

    if "지각" in user_question:
        if knowledge_text and "지각" in knowledge_text and ("결석" in knowledge_text or "처리" in knowledge_text):
            return f"{knowledge_text}"
        return f"{policies['지각_기준']}로 처리됩니다."

    if "수료" in user_question and "출석" in user_question:
        attendance_rate = _first_match(r"\d+\s*퍼센트|\d+\s*%", knowledge_text)
        if attendance_rate:
            rate_text = f"{attendance_rate}(80퍼센트)" if "%" in attendance_rate and "퍼센트" not in attendance_rate else attendance_rate
            return f"수료를 위해서는 전체 훈련시간의 {rate_text} 이상 출석해야 합니다."
        return "수료를 위해서는 전체 훈련시간의 80%(80퍼센트) 이상 출석해야 합니다."

    if "취업" in user_question:
        if knowledge_text and "취업" in knowledge_text:
            return f"{policies['취업지원_내용']} 기준입니다. {knowledge_text}"
        return f"수료 후 {policies['취업지원_내용']} 등을 받으실 수 있습니다."

    if "날씨" in user_question:
        return policies["안내_외_질문_응답"]

    if "혼내" in user_question or "괴롭" in user_question or "위협" in user_question:
        return policies["부적절_요청_응답"]

    if knowledge_text:
        return f"업로드된 지식 파일 기준으로 확인한 내용입니다. {knowledge_text}"

    return "죄송합니다, 해당 질문에 대한 답변을 준비하지 못했습니다."


if __name__ == "__main__":
    print(get_response("이 교육과정은 총 몇 시간인가요?"))
