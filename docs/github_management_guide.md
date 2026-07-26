# GitHub 관리 메뉴 사용 가이드

이 프로젝트의 Streamlit 대시보드는 다른 사용자가 저장소를 clone하거나 ZIP으로
전달받은 경우에도 `GitHub 관리 > 환경 설정`에서 Git 기본 환경을 준비할 수 있다.

## 준비 순서

1. 프로젝트 대시보드를 실행한다.
2. 상단의 `GitHub 관리` 메뉴를 선택한다.
3. `환경 설정`에서 Git 설치, 저장소, 사용자 정보, origin 상태를 확인한다.
4. Git 사용자 이름과 이메일을 입력한다.
5. 사용할 GitHub 저장소의 HTTPS 또는 SSH 주소를 입력한다.
6. ZIP으로 받은 폴더라면 저장소 초기화 항목에 동의한다.
7. `환경 정보 등록`을 선택한다.
8. `GitHub 연결 확인`으로 원격 저장소 접근 상태를 점검한다.

## 설정 저장 범위

- 사용자 이름과 이메일은 현재 프로젝트의 `.git/config`에만 저장된다.
- 다른 프로젝트에 적용되는 전역 Git 설정은 변경하지 않는다.
- `origin`이 이미 있으면 입력한 주소로 갱신하고, 없으면 새로 등록한다.
- ZIP 폴더 초기화 시 기본 브랜치는 `main`으로 설정한다.

## 인증정보 관리

GitHub 개인 액세스 토큰이나 비밀번호는 Git 환경 등록 화면에 저장하지 않는다.
HTTPS push 인증은 Git Credential Manager를 권장한다. `GITHUB_TOKEN` 또는
`GH_TOKEN`은 향후 GitHub API 기능에서 사용할 수 있지만 Git 명령의 인증을
자동으로 대신하지는 않는다. 토큰을 소스코드, 커밋, 문서 또는 공유 화면에
기록하면 안 된다.

## 지원하는 원격 주소

```text
https://github.com/OWNER/REPOSITORY.git
git@github.com:OWNER/REPOSITORY.git
ssh://git@github.com/OWNER/REPOSITORY.git
```

`저장소 현황`에서는 현재 브랜치, origin, 커밋 사용자, 변경 파일과 최근 커밋을
읽기 전용으로 확인할 수 있다.
