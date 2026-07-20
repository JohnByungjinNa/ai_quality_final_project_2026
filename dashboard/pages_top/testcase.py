def render_testcase_page(sub_menu, upload_page, execution_page, history_page, pytest_result_page):
    if sub_menu == "테스트케이스 업로드":
        upload_page()
        return True

    if sub_menu == "테스트 케이스 실행":
        execution_page()
        return True

    if sub_menu == "테스트 수행 이력":
        history_page()
        return True

    if sub_menu == "자동 테스트 결과":
        pytest_result_page()
        return True

    return False
