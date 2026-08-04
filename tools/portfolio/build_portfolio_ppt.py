from __future__ import annotations

import shutil
from pathlib import Path

import win32com.client


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "docs" / "portfolio"
PPTX_PATH = OUTPUT_DIR / "AWS_VOC_MULTI_AGENT_QA_PORTFOLIO.pptx"
PDF_PATH = OUTPUT_DIR / "AWS_VOC_MULTI_AGENT_QA_PORTFOLIO.pdf"
PREVIEW_DIR = ROOT / ".artifacts" / "portfolio_preview"
AGENT_SCREENSHOT = ROOT / ".artifacts" / "demo" / "02-agent-management.png"

SLIDE_W = 960
SLIDE_H = 540

NAVY = "0A2342"
NAVY_2 = "12355B"
BLUE = "1769E0"
BLUE_2 = "3B82F6"
CYAN = "24B6D2"
MINT = "2EC4A6"
GREEN = "16A36A"
ORANGE = "F59E0B"
RED = "DF4C4C"
PURPLE = "7C5CE7"
INK = "17243A"
MUTED = "66758A"
LIGHT = "F4F7FB"
LIGHT_BLUE = "EAF2FE"
LINE = "D7E1EE"
WHITE = "FFFFFF"


def color(value: str) -> int:
    value = value.lstrip("#")
    red, green, blue = int(value[:2], 16), int(value[2:4], 16), int(value[4:], 16)
    return red + green * 256 + blue * 65536


def alpha(value: float) -> float:
    """Normalize percentage-style transparency for the PowerPoint COM API."""
    return value / 100 if value > 1 else value


def set_font(text_range, *, size=18, bold=False, font_color=INK, name="맑은 고딕"):
    text_range.Font.Name = name
    text_range.Font.NameFarEast = name
    text_range.Font.Size = size
    text_range.Font.Bold = -1 if bold else 0
    text_range.Font.Fill.ForeColor.RGB = color(font_color)


def add_text(
    slide,
    text,
    x,
    y,
    w,
    h,
    *,
    size=18,
    bold=False,
    font_color=INK,
    align=1,
    valign=1,
    margin=0,
    fill=None,
    line=None,
    radius=False,
    transparency=0,
):
    shape_type = 5 if radius else 1
    shape = slide.Shapes.AddShape(shape_type, x, y, w, h)
    shape.Fill.Visible = -1 if fill else 0
    if fill:
        shape.Fill.ForeColor.RGB = color(fill)
        shape.Fill.Transparency = alpha(transparency)
    shape.Line.Visible = -1 if line else 0
    if line:
        shape.Line.ForeColor.RGB = color(line)
        shape.Line.Weight = 1
    frame = shape.TextFrame2
    frame.TextRange.Text = text
    frame.MarginLeft = margin
    frame.MarginRight = margin
    frame.MarginTop = margin
    frame.MarginBottom = margin
    frame.VerticalAnchor = valign
    frame.WordWrap = -1
    frame.AutoSize = 0
    frame.TextRange.ParagraphFormat.Alignment = align
    set_font(frame.TextRange, size=size, bold=bold, font_color=font_color)
    return shape


def add_line(slide, x1, y1, x2, y2, *, line_color=LINE, weight=1.5, arrow=False, transparency=0):
    line = slide.Shapes.AddLine(x1, y1, x2, y2)
    line.Line.ForeColor.RGB = color(line_color)
    line.Line.Weight = weight
    line.Line.Transparency = alpha(transparency)
    if arrow:
        line.Line.EndArrowheadStyle = 3
    return line


def add_background(slide, fill):
    background = slide.Shapes.AddShape(1, 0, 0, SLIDE_W, SLIDE_H)
    background.Fill.ForeColor.RGB = color(fill)
    background.Fill.Solid()
    background.Line.Visible = 0
    background.ZOrder(1)
    return background


def add_circle(slide, text, x, y, size, *, fill=BLUE, font_color=WHITE, font_size=14, line=None):
    shape = slide.Shapes.AddShape(9, x, y, size, size)
    shape.Fill.ForeColor.RGB = color(fill)
    shape.Line.Visible = -1 if line else 0
    if line:
        shape.Line.ForeColor.RGB = color(line)
    shape.TextFrame2.TextRange.Text = text
    shape.TextFrame2.VerticalAnchor = 3
    shape.TextFrame2.TextRange.ParagraphFormat.Alignment = 2
    set_font(shape.TextFrame2.TextRange, size=font_size, bold=True, font_color=font_color)
    return shape


def add_title(slide, title, subtitle=None, *, section="PORTFOLIO"):
    add_text(slide, section, 44, 20, 180, 20, size=9, bold=True, font_color=BLUE)
    add_text(slide, title, 44, 43, 870, 44, size=25, bold=True, font_color=NAVY)
    add_line(slide, 44, 96, 916, 96, line_color=LINE, weight=1)
    if subtitle:
        add_text(slide, subtitle, 44, 103, 870, 28, size=11, font_color=MUTED)


def add_footer(slide, number):
    add_line(slide, 44, 512, 916, 512, line_color=LINE, weight=0.8)
    add_text(slide, "AWS VOC MULTI-AGENT QA", 44, 517, 240, 14, size=8, bold=True, font_color=MUTED)
    add_text(slide, f"{number:02d}", 880, 516, 36, 14, size=8, bold=True, font_color=BLUE, align=3)


def add_card(slide, x, y, w, h, *, fill=WHITE, line=LINE, accent=None):
    card = slide.Shapes.AddShape(5, x, y, w, h)
    card.Fill.ForeColor.RGB = color(fill)
    card.Line.ForeColor.RGB = color(line)
    card.Line.Weight = 1
    card.Shadow.Visible = -1
    card.Shadow.ForeColor.RGB = color(NAVY)
    card.Shadow.Transparency = alpha(88)
    card.Shadow.Blur = 8
    card.Shadow.OffsetX = 1
    card.Shadow.OffsetY = 3
    if accent:
        bar = slide.Shapes.AddShape(1, x, y, 6, h)
        bar.Fill.ForeColor.RGB = color(accent)
        bar.Line.Visible = 0
    return card


def add_metric(slide, x, y, w, label, value, detail, *, accent=BLUE):
    add_card(slide, x, y, w, 112, fill=WHITE, line=LINE, accent=accent)
    add_text(slide, label, x + 20, y + 16, w - 34, 20, size=10, bold=True, font_color=MUTED)
    add_text(slide, value, x + 20, y + 40, w - 34, 34, size=22, bold=True, font_color=accent)
    add_text(slide, detail, x + 20, y + 80, w - 34, 18, size=9, font_color=MUTED)


def add_bullet_list(slide, items, x, y, w, *, size=15, color_value=INK, bullet_color=BLUE, gap=38):
    for index, item in enumerate(items):
        yy = y + index * gap
        add_circle(slide, "", x, yy + 6, 8, fill=bullet_color)
        add_text(slide, item, x + 18, yy, w - 18, gap - 2, size=size, font_color=color_value, valign=1)


def add_pill(slide, text, x, y, w, *, fill=LIGHT_BLUE, font_color=BLUE):
    return add_text(
        slide,
        text,
        x,
        y,
        w,
        24,
        size=9,
        bold=True,
        font_color=font_color,
        align=2,
        valign=3,
        margin=2,
        fill=fill,
        line=fill,
        radius=True,
    )


def slide_cover(pres):
    slide = pres.Slides.Add(1, 12)
    add_background(slide, NAVY)

    for x, y, size, fill, opacity in [
        (700, -110, 320, BLUE, 45),
        (785, 80, 230, CYAN, 65),
        (-100, 365, 260, PURPLE, 78),
    ]:
        circle = slide.Shapes.AddShape(9, x, y, size, size)
        circle.Fill.ForeColor.RGB = color(fill)
        circle.Fill.Transparency = alpha(opacity)
        circle.Line.Visible = 0

    add_pill(slide, "AI QA · LLMOps · Operational Audit", 58, 54, 270, fill=NAVY_2, font_color="B9D6FF")
    add_text(
        slide,
        "AWS 기반 VOC 멀티 에이전트\nQA 결과관리 및 운영감사 프로젝트",
        58,
        116,
        720,
        142,
        size=34,
        bold=True,
        font_color=WHITE,
    )
    add_text(
        slide,
        "VOC 근거 수집부터 독립 평가, 실행 타당성 검증, 사람 승인과\nAWS S3 증적 보관까지 연결한 Evidence-first 품질관리 플랫폼",
        60,
        280,
        630,
        62,
        size=15,
        font_color="C9D9ED",
    )
    labels = [("6", "gRPC Agent"), ("3", "LLM Provider"), ("100", "Validity Rubric"), ("S3", "Audit Evidence")]
    for idx, (value, label) in enumerate(labels):
        x = 60 + idx * 168
        add_text(slide, value, x, 382, 148, 42, size=24, bold=True, font_color=WHITE, align=2, valign=3, fill=NAVY_2, line="355A82", radius=True)
        add_text(slide, label, x, 430, 148, 18, size=9, font_color="B7CBE2", align=2)
    add_text(slide, "최강3조  ·  2026.07–08  ·  작성자 이름 입력", 60, 490, 620, 18, size=10, font_color="AFC3DB")
    add_text(slide, "01", 882, 494, 38, 16, size=9, bold=True, font_color="AFC3DB", align=3)
    return slide


def slide_problem(pres):
    slide = pres.Slides.Add(2, 12)
    add_title(slide, "좋은 AI 답변이 곧 실행 가능한 개선안은 아닙니다", "VOC 분석의 마지막 1마일: 근거, 실행 계획, 위험과 책임")
    problems = [
        ("01", "근거 단절", "개선안이 어떤 VOC 원문과 Trace에서 나왔는지 재현하기 어렵습니다.", RED),
        ("02", "자기평가 편향", "생성과 평가를 같은 모델이 수행하면 높은 점수를 스스로 정당화할 수 있습니다.", ORANGE),
        ("03", "실행 정보 누락", "담당·일정·KPI·적용 범위가 없는 개선안도 자연스럽게 보입니다.", PURPLE),
        ("04", "승인 책임 불명확", "AI PASS와 실제 운영 승인이 섞이면 적용 책임과 감사 근거가 사라집니다.", BLUE),
    ]
    for index, (number, title, detail, accent) in enumerate(problems):
        col, row = index % 2, index // 2
        x, y = 48 + col * 438, 142 + row * 150
        add_card(slide, x, y, 410, 126, accent=accent)
        add_circle(slide, number, x + 22, y + 24, 44, fill=accent, font_size=12)
        add_text(slide, title, x + 82, y + 20, 290, 28, size=17, bold=True, font_color=NAVY)
        add_text(slide, detail, x + 82, y + 53, 292, 58, size=11, font_color=MUTED)
    add_text(slide, "핵심 질문", 50, 450, 86, 24, size=10, bold=True, font_color=WHITE, align=2, valign=3, fill=BLUE, line=BLUE, radius=True)
    add_text(slide, "이 개선안을 실제 업무에 적용하고, 측정하고, 책임질 수 있는가?", 150, 446, 700, 34, size=19, bold=True, font_color=NAVY)
    add_footer(slide, 2)


def slide_goal(pres):
    slide = pres.Slides.Add(3, 12)
    add_title(slide, "프로젝트 목표", "그럴듯한 개선안이 아니라 실행하고 측정하며 책임질 수 있는 개선안만 운영으로 연결")
    goals = [
        ("01", "근거 연결", "VOC 원문", "Run · Case · Trace", "판단을 다시 추적할 수 있게"),
        ("02", "실행 가능성", "담당 · 일정 · KPI", "적용 범위 · 위험", "현장에서 실행 가능한 수준으로"),
        ("03", "책임 있는 적용", "AI 자동 평가", "QA · 업무 승인", "자동화와 사람 책임을 분리"),
    ]
    accents = [BLUE, MINT, PURPLE]
    for idx, goal in enumerate(goals):
        x = 48 + idx * 294
        add_card(slide, x, 148, 270, 278, fill=WHITE, line=LINE, accent=accents[idx])
        add_circle(slide, goal[0], x + 24, 172, 48, fill=accents[idx], font_size=13)
        add_text(slide, goal[1], x + 24, 234, 220, 32, size=19, bold=True, font_color=NAVY)
        add_text(slide, goal[2], x + 24, 286, 220, 24, size=13, bold=True, font_color=accents[idx])
        add_text(slide, goal[3], x + 24, 316, 220, 24, size=13, bold=True, font_color=accents[idx])
        add_line(slide, x + 24, 352, x + 236, 352, line_color=LINE)
        add_text(slide, goal[4], x + 24, 367, 220, 42, size=11, font_color=MUTED)
    add_text(slide, "WHY THIS PROCESS", 350, 458, 260, 20, size=9, bold=True, font_color=BLUE, align=2)
    add_text(slide, "AI가 답을 만드는 시스템 → AI의 판단을 검증하는 시스템", 190, 478, 580, 25, size=16, bold=True, font_color=NAVY, align=2)
    add_footer(slide, 3)


def slide_process(pres):
    slide = pres.Slides.Add(4, 12)
    add_title(slide, "품질 Gate 기반 E2E 프로세스", "각 단계의 상태와 증적을 분리하고 미달 시 보완·RETEST로 되돌립니다")
    steps = [
        ("VOC", "고객 불만", BLUE),
        ("6A", "Agent Pipeline", CYAN),
        ("J", "독립 Judge", PURPLE),
        ("V", "타당성 평가", MINT),
        ("QA", "QA 검토", ORANGE),
        ("B", "업무 승인", GREEN),
        ("AWS", "운영 증적", NAVY_2),
    ]
    for idx, (mark, label, accent) in enumerate(steps):
        x = 42 + idx * 128
        add_circle(slide, mark, x, 185, 62, fill=accent, font_size=12)
        add_text(slide, label, x - 18, 258, 98, 34, size=11, bold=True, font_color=NAVY, align=2)
        if idx < len(steps) - 1:
            add_line(slide, x + 66, 216, x + 118, 216, line_color="9DB5CF", weight=2, arrow=True)
    add_card(slide, 92, 335, 776, 110, fill=LIGHT, line=LINE)
    add_text(slide, "보완 루프", 116, 355, 104, 24, size=12, bold=True, font_color=RED)
    add_text(slide, "REVIEW_REQUIRED · ERROR · REJECTED", 230, 355, 280, 24, size=12, bold=True, font_color=NAVY)
    add_text(slide, "실패를 PASS로 덮지 않고 원본 Run과 연결된 RETEST에서 같은 조건으로 재검증", 116, 390, 700, 30, size=13, font_color=MUTED)
    add_line(slide, 680, 332, 286, 332, line_color=RED, weight=2, arrow=True)
    add_footer(slide, 4)


def slide_architecture(pres):
    slide = pres.Slides.Add(5, 12)
    add_title(slide, "AWS 기반 결과관리 아키텍처", "Streamlit UI, gRPC Agent, 독립 평가와 Run 증적을 하나의 감사 체인으로 연결")

    lanes = [("Experience", 135, 60), ("AI Quality", 255, 60), ("Evidence & Audit", 385, 60)]
    for name, y, h in lanes:
        add_text(slide, name.upper(), 44, y, 108, h, size=8, bold=True, font_color=MUTED, valign=3)
        band = slide.Shapes.AddShape(5, 152, y, 764, h)
        band.Fill.ForeColor.RGB = color(LIGHT)
        band.Line.ForeColor.RGB = color(LINE)

    nodes = [
        ("Streamlit\nDashboard", 180, 146, 150, 40, BLUE),
        ("FastAPI\nqa-observer", 365, 146, 150, 40, CYAN),
        ("Jira · GitHub", 550, 146, 150, 40, PURPLE),
        ("AWS Session", 735, 146, 150, 40, NAVY_2),
        ("gRPC Orchestrator", 180, 266, 150, 50, NAVY_2),
        ("6 Agent Pipeline", 365, 266, 150, 50, BLUE),
        ("Independent Judge", 550, 266, 150, 50, PURPLE),
        ("Validity + Approval", 735, 266, 150, 50, MINT),
        ("Run · Case · Trace", 180, 396, 180, 48, BLUE),
        ("Rubric · Hash", 390, 396, 150, 48, CYAN),
        ("Audit Manifest", 570, 396, 150, 48, ORANGE),
        ("AWS S3 Evidence", 750, 396, 150, 48, GREEN),
    ]
    for text, x, y, w, h, accent in nodes:
        add_text(slide, text, x, y, w, h, size=11, bold=True, font_color=WHITE, align=2, valign=3, fill=accent, line=accent, radius=True, margin=4)

    for x1, y1, x2, y2 in [
        (330, 166, 365, 166), (515, 166, 550, 166), (700, 166, 735, 166),
        (330, 291, 365, 291), (515, 291, 550, 291), (700, 291, 735, 291),
        (360, 420, 390, 420), (540, 420, 570, 420), (720, 420, 750, 420),
    ]:
        add_line(slide, x1, y1, x2, y2, line_color="9DB5CF", weight=1.7, arrow=True)
    for x in [255, 440, 625, 810]:
        add_line(slide, x, 190, x, 258, line_color="9DB5CF", weight=1.4, arrow=True)
    for x in [255, 440, 625, 810]:
        add_line(slide, x, 319, x, 387, line_color="9DB5CF", weight=1.4, arrow=True)
    add_footer(slide, 5)


def slide_agents(pres):
    slide = pres.Slides.Add(6, 12)
    add_title(slide, "6개 Agent로 책임과 실패 지점을 분리", "Agent 수보다 중요한 것은 역할·상태·Trace를 독립적으로 확인할 수 있다는 점입니다")
    add_card(slide, 46, 132, 540, 342, fill=WHITE, line=LINE)
    if AGENT_SCREENSHOT.exists():
        picture = slide.Shapes.AddPicture(str(AGENT_SCREENSHOT), 0, -1, 60, 145, 512, 316)
        picture.Line.Visible = -1
        picture.Line.ForeColor.RGB = color(LINE)
    roles = [
        ("01", "Interpreter", "질문 의도·검색 조건", BLUE),
        ("02", "Retriever", "VOC 원문 근거", MINT),
        ("03", "Summarizer", "요약·흐름 제어", CYAN),
        ("04", "Evaluator", "후보 상대평가", PURPLE),
        ("05", "Critic", "누락·위험 탐지", ORANGE),
        ("06", "Improver", "실행 개선안 생성", GREEN),
    ]
    for idx, (num, name, role, accent) in enumerate(roles):
        y = 128 + idx * 61
        add_circle(slide, num, 620, y + 4, 32, fill=accent, font_size=9)
        add_text(slide, name, 665, y, 120, 21, size=12, bold=True, font_color=NAVY)
        add_text(slide, role, 665, y + 23, 200, 19, size=9, font_color=MUTED)
    add_footer(slide, 6)


def slide_judge(pres):
    slide = pres.Slides.Add(7, 12)
    add_title(slide, "독립 LLM Judge로 자기평가 편향 보완", "Pipeline 내부 평가와 최종 평가의 Provider·모델·Rubric을 분리")
    add_card(slide, 48, 142, 362, 286, fill=LIGHT, line=LINE)
    add_text(slide, "PIPELINE 내부", 72, 164, 140, 20, size=9, bold=True, font_color=MUTED)
    add_circle(slide, "E", 88, 216, 70, fill=BLUE, font_size=20)
    add_text(slide, "Evaluator", 176, 216, 160, 26, size=17, bold=True, font_color=NAVY)
    add_text(slide, "후보 간 상대평가", 176, 247, 160, 22, size=11, font_color=MUTED)
    add_circle(slide, "C", 88, 310, 70, fill=ORANGE, font_size=20)
    add_text(slide, "Critic", 176, 310, 160, 26, size=17, bold=True, font_color=NAVY)
    add_text(slide, "누락·모순·위험 검토", 176, 341, 170, 22, size=11, font_color=MUTED)

    add_line(slide, 430, 285, 505, 285, line_color=PURPLE, weight=3, arrow=True)
    add_text(slide, "독립 평가", 432, 248, 70, 20, size=9, bold=True, font_color=PURPLE, align=2)

    add_card(slide, 526, 142, 386, 286, fill=WHITE, line=PURPLE, accent=PURPLE)
    add_text(slide, "INDEPENDENT JUDGE", 554, 164, 220, 20, size=9, bold=True, font_color=PURPLE)
    add_text(slide, "별도 Provider · 모델", 554, 205, 290, 28, size=19, bold=True, font_color=NAVY)
    add_text(slide, "100점 Rubric · 차원별 근거 · 독립성 등급", 554, 242, 310, 28, size=11, font_color=MUTED)
    add_metric(slide, 554, 292, 150, "최종 시연", "96점", "PASS", accent=PURPLE)
    add_metric(slide, 724, 292, 150, "독립성", "A", "Provider 분리", accent=GREEN)
    add_text(slide, "동일 계열 평가 91점·C → Provider 분리 후 96점·A", 192, 456, 576, 30, size=14, bold=True, font_color=NAVY, align=2, fill=LIGHT_BLUE, line=LIGHT_BLUE, radius=True)
    add_footer(slide, 7)


def slide_validity(pres):
    slide = pres.Slides.Add(8, 12)
    add_title(slide, "핵심 차별점 · 개선안 타당성 평가", "답변 품질을 넘어 실제 실행 가능성과 운영 위험을 100점 기준으로 검증")
    dimensions = [
        ("원인 ↔ 개선안", 22, BLUE),
        ("VOC · Trace 근거", 22, CYAN),
        ("업무·기술 실행", 18, MINT),
        ("담당·일정·KPI", 13, ORANGE),
        ("위험·보안·규제", 25, PURPLE),
    ]
    y = 145
    for label, score, accent in dimensions:
        add_text(slide, label, 54, y, 150, 22, size=11, bold=True, font_color=NAVY)
        bg = slide.Shapes.AddShape(5, 214, y + 2, 360, 16)
        bg.Fill.ForeColor.RGB = color("E6ECF4")
        bg.Line.Visible = 0
        bar = slide.Shapes.AddShape(5, 214, y + 2, 360 * score / 25, 16)
        bar.Fill.ForeColor.RGB = color(accent)
        bar.Line.Visible = 0
        add_text(slide, f"{score}점", 588, y - 2, 54, 22, size=11, bold=True, font_color=accent, align=3)
        y += 48

    add_card(slide, 678, 136, 234, 250, fill=NAVY, line=NAVY)
    add_text(slide, "SERVER-SIDE DECISION", 700, 158, 190, 18, size=8, bold=True, font_color="AFCBEB", align=2)
    add_text(slide, "80점 이상", 700, 196, 190, 34, size=24, bold=True, font_color=WHITE, align=2)
    add_text(slide, "+ 모든 항목 하한 충족\n+ 즉시 보류 규칙 0건", 708, 238, 174, 56, size=12, font_color="D6E5F6", align=2)
    add_text(slide, "AI_PASS", 718, 318, 154, 40, size=20, bold=True, font_color=WHITE, align=2, valign=3, fill=GREEN, line=GREEN, radius=True)

    add_card(slide, 54, 414, 858, 72, fill="FFF7E7", line="F8D89A", accent=ORANGE)
    add_text(slide, "즉시 승인 보류", 80, 431, 130, 24, size=12, bold=True, font_color=ORANGE)
    add_text(slide, "근거 누락  ·  안전·규제 위험  ·  High/Critical 결함  ·  Judge 미통과  ·  기준 대비 안전성 하락", 220, 429, 660, 30, size=12, font_color=NAVY)
    add_footer(slide, 8)


def slide_audit(pres):
    slide = pres.Slides.Add(9, 12)
    add_title(slide, "Run부터 AWS S3까지 이어지는 운영감사 체인", "누가, 언제, 어떤 근거로 판단했는지 재현 가능한 Evidence-first 설계")
    stages = [
        ("RUN", "Run ID\n실행 상태", BLUE),
        ("CASE", "Case 결과\nTC·질문", CYAN),
        ("TRACE", "A2A 이벤트\nAgent 호출", MINT),
        ("RUBRIC", "버전·Hash\n점수 근거", PURPLE),
        ("APPROVAL", "QA·업무\n감사 이력", ORANGE),
        ("AWS", "Manifest\nSHA-256", GREEN),
    ]
    for idx, (mark, detail, accent) in enumerate(stages):
        x = 46 + idx * 148
        add_circle(slide, mark, x + 27, 154, 70, fill=accent, font_size=10)
        add_text(slide, detail, x, 238, 124, 48, size=11, bold=True, font_color=NAVY, align=2)
        if idx < len(stages) - 1:
            add_line(slide, x + 103, 189, x + 144, 189, line_color="9DB5CF", weight=1.7, arrow=True)
    add_card(slide, 90, 338, 780, 108, fill=LIGHT, line=LINE)
    rules = [
        ("허용 파일", "step10_acceptance.json · .md"),
        ("업로드 보호", "5 MB 제한 · 비밀값 패턴 검사 · AES256"),
        ("원격 검증", "Manifest와 각 파일의 크기·SHA-256 재검증"),
    ]
    for idx, (label, detail) in enumerate(rules):
        x = 112 + idx * 248
        add_text(slide, label, x, 358, 220, 20, size=10, bold=True, font_color=GREEN)
        add_text(slide, detail, x, 385, 220, 40, size=10, font_color=MUTED)
    add_footer(slide, 9)


def slide_integrations(pres):
    slide = pres.Slides.Add(10, 12)
    add_title(slide, "품질 결과를 업무·형상·증적 관리로 연결", "외부 시스템 변경은 사용자의 명시적 액션에서만 수행")
    integrations = [
        ("J", "Jira", "JQL 조회\n신규 이슈 등록\n등록 감사 이력", BLUE, "업무 실행"),
        ("G", "GitHub", "저장소·브랜치\n저장·다운로드\n충돌 사전 점검", PURPLE, "형상 관리"),
        ("AWS", "AWS S3", "최종 인수 증적\nAES256 업로드\n원격 SHA-256", GREEN, "운영 감사"),
    ]
    for idx, (mark, name, detail, accent, role) in enumerate(integrations):
        x = 58 + idx * 298
        add_card(slide, x, 150, 270, 292, fill=WHITE, line=LINE, accent=accent)
        add_circle(slide, mark, x + 28, 174, 58, fill=accent, font_size=13)
        add_pill(slide, role, x + 152, 184, 92, fill=LIGHT_BLUE if idx < 2 else "E8F7F1", font_color=accent)
        add_text(slide, name, x + 28, 250, 210, 32, size=22, bold=True, font_color=NAVY)
        add_text(slide, detail, x + 28, 302, 210, 82, size=13, font_color=MUTED)
        add_text(slide, "명시적 사용자 동작", x + 28, 402, 210, 20, size=10, bold=True, font_color=accent)
    add_footer(slide, 10)


def slide_results(pres):
    slide = pres.Slides.Add(11, 12)
    add_title(slide, "최종 시연 결과와 정직한 품질 판정", "대표 E2E 승인과 35건 전체 운영 인수 Gate를 구분")
    metrics = [
        ("PIPELINE", "PASS", "오류 0건", BLUE),
        ("JUDGE", "96점", "PASS · 독립성 A", PURPLE),
        ("VALIDITY", "81점", "AI_PASS", MINT),
        ("APPROVAL", "승인", "BUSINESS_APPROVED", GREEN),
    ]
    for idx, (label, value, detail, accent) in enumerate(metrics):
        add_metric(slide, 46 + idx * 222, 140, 202, label, value, detail, accent=accent)
    add_card(slide, 46, 282, 418, 176, fill="EAF7F1", line="B7E6D3", accent=GREEN)
    add_text(slide, "대표 TC-01 E2E", 72, 302, 200, 24, size=12, bold=True, font_color=GREEN)
    add_text(slide, "FORMAL QUALITY\nAPPROVED", 72, 338, 330, 60, size=24, bold=True, font_color=NAVY)
    add_text(slide, "Run  RUN-20260804-132006-496046-e9c0", 72, 416, 340, 18, size=9, font_color=MUTED)

    add_card(slide, 492, 282, 422, 176, fill="FFF7E7", line="F6D697", accent=ORANGE)
    add_text(slide, "35건 최종 운영 인수", 518, 302, 220, 24, size=12, bold=True, font_color=ORANGE)
    add_text(slide, "4 PASS / 6 HOLD", 518, 345, 330, 36, size=24, bold=True, font_color=NAVY)
    add_text(slide, "미실행·미검증·잔여 위험을 성공으로 확대 해석하지 않음", 518, 398, 350, 38, size=10, font_color=MUTED)
    add_text(slide, "Step 10 회귀 229 PASS  ·  기존 관측 집계 결함 6건은 잔여 결함으로 분리", 132, 476, 696, 20, size=10, bold=True, font_color=NAVY, align=2)
    add_footer(slide, 11)


def slide_closing(pres):
    slide = pres.Slides.Add(12, 12)
    add_background(slide, NAVY)
    add_text(slide, "PROJECT OUTCOME", 58, 46, 180, 22, size=9, bold=True, font_color="8FC1FF")
    add_text(slide, "AI가 답을 만드는 시스템에서,\nAI의 판단을 검증하고 책임 있게 운영하는 시스템으로.", 58, 98, 820, 94, size=30, bold=True, font_color=WHITE)
    outcomes = [
        ("01", "독립성", "생성과 평가의 Provider·역할 분리"),
        ("02", "실행 가능성", "타당성 Rubric과 서버 재판정"),
        ("03", "책임", "QA·업무 승인과 감사 이력"),
        ("04", "증적", "Run·Trace·AWS 원격 무결성"),
    ]
    for idx, (num, title, detail) in enumerate(outcomes):
        x = 58 + (idx % 2) * 420
        y = 240 + (idx // 2) * 112
        add_circle(slide, num, x, y, 48, fill=BLUE if idx % 2 == 0 else MINT, font_size=11)
        add_text(slide, title, x + 66, y - 2, 300, 26, size=16, bold=True, font_color=WHITE)
        add_text(slide, detail, x + 66, y + 30, 310, 30, size=11, font_color="BFD0E3")
    add_text(slide, "NEXT", 58, 456, 56, 22, size=9, bold=True, font_color="8FC1FF")
    add_text(slide, "동일 조건 35건 최종 승인 · 관측 결함 해소 · 조직 계정 기반 역할 권한", 126, 454, 700, 24, size=12, font_color="D7E6F6")
    add_text(slide, "THANK YOU", 794, 492, 126, 18, size=10, bold=True, font_color="8FC1FF", align=3)
    return slide


def build_deck():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if PREVIEW_DIR.exists():
        shutil.rmtree(PREVIEW_DIR)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    app = win32com.client.DispatchEx("PowerPoint.Application")
    app.Visible = True
    presentation = app.Presentations.Add()
    presentation.PageSetup.SlideWidth = SLIDE_W
    presentation.PageSetup.SlideHeight = SLIDE_H

    try:
        slide_cover(presentation)
        slide_problem(presentation)
        slide_goal(presentation)
        slide_process(presentation)
        slide_architecture(presentation)
        slide_agents(presentation)
        slide_judge(presentation)
        slide_validity(presentation)
        slide_audit(presentation)
        slide_integrations(presentation)
        slide_results(presentation)
        slide_closing(presentation)

        presentation.SaveAs(str(PPTX_PATH), 24)
        presentation.SaveAs(str(PDF_PATH), 32)
        for index in range(1, presentation.Slides.Count + 1):
            path = PREVIEW_DIR / f"slide-{index:02d}.png"
            presentation.Slides(index).Export(str(path), "PNG", 1600, 900)
    finally:
        presentation.Close()
        app.Quit()

    print(f"PPTX={PPTX_PATH}")
    print(f"PDF={PDF_PATH}")
    print(f"PREVIEW={PREVIEW_DIR}")


if __name__ == "__main__":
    build_deck()
