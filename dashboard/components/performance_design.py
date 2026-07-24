from html import escape

import streamlit as st


def render_performance_design_styles():
    st.markdown(
        """
        <style>
        .pfd-hero,.pfd-section-head,.pfd-card-grid,.pfd-service-label{
            font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;color:#15243b
        }
        .pfd-hero{display:flex;align-items:center;gap:15px;border:1px solid #c8d9ee;border-left:5px solid #155a96;
            border-radius:9px;background:linear-gradient(110deg,#f5faff,#fff);padding:14px 17px;margin:3px 0 13px;
            box-shadow:0 4px 14px rgba(22,78,128,.06);box-sizing:border-box;width:100%}
        .pfd-hero-icon{display:flex;width:46px;min-width:46px;color:#155a96}.pfd-hero-icon svg{width:100%;height:auto}
        .pfd-hero-title{font-size:21px;font-weight:850;color:#073b72;letter-spacing:-.4px}.pfd-hero p{margin:3px 0 0;color:#53657c;font-size:12px}
        .pfd-section-head{display:flex;align-items:center;gap:10px;margin:20px 0 9px;padding-bottom:8px;border-bottom:1px solid #dbe6f2;width:100%}
        .pfd-section-icon{display:flex;width:30px;height:30px;min-width:30px;padding:5px;border-radius:8px;color:#155a96;background:#eaf3fb;box-sizing:border-box}
        .pfd-section-icon svg{width:100%;height:auto}.pfd-section-copy{min-width:0}.pfd-section-title{font-size:16px;font-weight:850;color:#173f68;line-height:1.2}
        .pfd-section-desc{font-size:10px;color:#718096;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .pfd-card-grid{display:grid;grid-template-columns:repeat(var(--pfd-cols,4),minmax(0,1fr));gap:10px;margin:2px 0 12px;width:100%}
        .pfd-card{height:88px;border:1px solid #c8d9ee;border-radius:8px;background:linear-gradient(145deg,#fff,#f8fbff);display:flex;align-items:center;gap:10px;padding:10px 12px;box-sizing:border-box;min-width:0;box-shadow:0 3px 10px rgba(22,78,128,.05)}
        .pfd-card-icon{display:flex;width:34px;min-width:34px;color:#155a96}.pfd-card-icon svg{width:100%;height:auto}.pfd-card-copy{min-width:0}
        .pfd-card-label{display:block;color:#40536d;font-size:10px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pfd-card strong{display:block;color:#073b72;font-size:19px;line-height:1.14;margin:4px 0 2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pfd-card small{display:block;color:#728095;font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .pfd-card.good .pfd-card-icon,.pfd-card.good strong{color:#299049}.pfd-card.warn .pfd-card-icon,.pfd-card.warn strong{color:#b36a08}.pfd-card.bad .pfd-card-icon,.pfd-card.bad strong{color:#d83f36}
        .pfd-service-label{display:flex;align-items:center;gap:8px;min-width:0}.pfd-service-label i{display:flex;width:25px;min-width:25px;color:#155a96}.pfd-service-label svg{width:100%;height:auto}.pfd-service-label b{color:#173f68;white-space:nowrap}
        @media(max-width:1100px){.pfd-card-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:720px){.pfd-hero{align-items:flex-start}.pfd-card-grid{grid-template-columns:1fr}.pfd-section-desc{white-space:normal}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_hero(icon, title, description):
    st.markdown(
        f"<div class='pfd-hero'><span class='pfd-hero-icon'>{performance_svg_icon(icon)}</span>"
        f"<div><div class='pfd-hero-title'>{escape(title)}</div><p>{escape(description)}</p></div></div>",
        unsafe_allow_html=True,
    )


def render_section_header(icon, title, description):
    st.markdown(
        f"<div class='pfd-section-head'><span class='pfd-section-icon'>{performance_svg_icon(icon)}</span>"
        f"<div class='pfd-section-copy'><div class='pfd-section-title'>{escape(title)}</div>"
        f"<div class='pfd-section-desc'>{escape(description)}</div></div></div>",
        unsafe_allow_html=True,
    )


def render_icon_cards(cards, columns=4):
    markup = "".join(
        f"<article class='pfd-card {escape(str(tone))}'><span class='pfd-card-icon'>{performance_svg_icon(icon)}</span>"
        f"<div class='pfd-card-copy'><span class='pfd-card-label'>{escape(str(label))}</span>"
        f"<strong>{escape(str(value))}</strong><small>{escape(str(detail or ''))}</small></div></article>"
        for icon, label, value, detail, tone in cards
    )
    st.markdown(
        f"<div class='pfd-card-grid' style='--pfd-cols:{int(columns)}'>{markup}</div>",
        unsafe_allow_html=True,
    )


def service_icon_label(service_name, icon=None):
    icon_name = icon or service_icon_name(service_name)
    return (
        f"<div class='pfd-service-label'><i>{performance_svg_icon(icon_name)}</i>"
        f"<b>{escape(str(service_name))}</b></div>"
    )


def service_icon_name(service_name):
    normalized = str(service_name).lower()
    if "docker" in normalized:
        return "docker"
    if "grafana" in normalized:
        return "grafana"
    if "prometheus" in normalized:
        return "prometheus"
    if "fastapi" in normalized:
        return "fastapi"
    if "chroma" in normalized or "db" in normalized:
        return "database"
    if "k6" in normalized:
        return "gauge"
    return "services"


def performance_svg_icon(name):
    paths = {
        "services": "<rect x='3' y='4' width='7' height='6' rx='1'/><rect x='14' y='4' width='7' height='6' rx='1'/><rect x='8.5' y='15' width='7' height='6' rx='1'/><path d='M6.5 10v2h11v-2m-5.5 2v3'/>",
        "docker": "<path d='M3 11h14v4h3c0 4-3 6-8 6H7c-2 0-4-2-4-5v-5Z'/><path d='M6 8h3v3H6zm4 0h3v3h-3zm4 0h3v3h-3zM10 4h3v3h-3z'/>",
        "grafana": "<circle cx='12' cy='12' r='8'/><path d='M12 4v4l3 2 3-1M7 18l3-4 4 2 3-4'/>",
        "prometheus": "<path d='M12 3c1 4-2 5-2 8 0 1.7 1 3 2 3s2-1.3 2-3c2 2 3 4 3 6a5 5 0 0 1-10 0c0-3 2-5 5-8'/><path d='M8 20h8'/>",
        "fastapi": "<path d='M13 2 5 13h6l-1 9 9-13h-6V2Z'/>",
        "gauge": "<path d='M4 18a8 8 0 1 1 16 0'/><path d='m12 18 5-7M7 18h10'/>",
        "settings": "<circle cx='12' cy='12' r='3'/><path d='M19 13.5v-3l-2-.7-.7-1.7.9-1.9-2.1-2.1-1.9.9-1.7-.7L10.5 2h-3l-.7 2-1.7.7-1.9-.9-2.1 2.1.9 1.9-.7 1.7-2 .7v3l2 .7.7 1.7-.9 1.9 2.1 2.1 1.9-.9 1.7.7.7 2h3l.7-2 1.7-.7 1.9.9 2.1-2.1-.9-1.9.7-1.7 2-.4Z' transform='scale(.8) translate(3 3)'/>",
        "duration": "<circle cx='12' cy='13' r='8'/><path d='M9 2h6m-3 3v8l4 2'/>",
        "history": "<path d='M4 12a8 8 0 1 0 2-5.3L4 9'/><path d='M4 4v5h5m3-2v6l4 2'/>",
        "database": "<ellipse cx='12' cy='5' rx='8' ry='3'/><path d='M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6'/>",
        "endpoint": "<circle cx='5' cy='12' r='2'/><circle cx='19' cy='6' r='2'/><circle cx='19' cy='18' r='2'/><path d='m7 11 10-4m-10 6 10 4'/>",
        "logs": "<path d='M5 3h14v18H5zM8 8h8m-8 4h8m-8 4h5'/>",
        "health": "<path d='M12 20S4 15.5 4 9.5A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 8 2.5C20 15.5 12 20 12 20Z'/><path d='M7 12h3l1-2 2 4 1-2h3'/>",
        "metrics": "<path d='M3 13h4l2-6 4 11 2-6h6'/><path d='M4 4h16v16H4z'/>",
        "request": "<path d='M4 7h13m-4-4 4 4-4 4M20 17H7m4-4-4 4 4 4'/>",
        "check": "<circle cx='12' cy='12' r='9'/><path d='m8 12 3 3 6-7'/>",
        "warning": "<path d='M12 3 2.8 20h18.4L12 3Z'/><path d='M12 9v5m0 3h.01'/>",
        "play": "<circle cx='12' cy='12' r='9'/><path d='m10 8 6 4-6 4V8Z'/>",
    }
    return (
        "<svg viewBox='0 0 24 24' aria-hidden='true' fill='none' stroke='currentColor' "
        "stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
        + paths[name]
        + "</svg>"
    )
