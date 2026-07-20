def render_knowledge_db_page(sub_menu, knowledge_base_page):
    if sub_menu in ("지식 파일 관리", "지식 베이스 관리"):
        knowledge_base_page()
        return True

    return False
