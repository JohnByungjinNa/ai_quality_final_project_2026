# AWS 환경 변경 기록

이 문서는 VOC 품질진단 AWS 연동을 위해 실제 계정에 적용한 변경과 검증 결과를 기록한다. 계정 ID, 이메일, Access Key, 세션 토큰과 기타 비밀값은 기록하지 않는다.

## 2026-08-03

### 12:45 KST · CLI와 작업 주체 준비

- AWS CLI v2 사용자 범위 설치: `2.36.14`
- 로컬 프로필 이름: `JohnNa-QA`
- 기본 작업 리전: `ap-northeast-2`
- 최초 세션 확인 결과: 로컬 프로필 이름과 달리 실제 호출 주체가 루트 사용자임을 확인
- 루트 MFA 활성화 확인
- 루트 Access Key 없음 확인
- IAM 사용자 `JohnNa-QA`의 콘솔 로그인과 MFA 활성화 확인
- IAM 사용자 `JohnNa-QA`에 `SignInLocalDevelopmentAccess` 연결
- IAM 사용자 `JohnNa-QA`에 환경 구축 기간에만 사용할 `AdministratorAccess` 임시 연결
- 기존 장기 Access Key 1개는 사용처가 확인되지 않아 변경하지 않음

검증:

- `SignInLocalDevelopmentAccess`: 연결됨
- 임시 `AdministratorAccess`: 연결됨
- 다음 작업: 루트 CLI 세션 종료 후 실제 IAM 사용자 `JohnNa-QA`로 재인증

롤백:

- 환경 구축과 UAT 완료 후 `AdministratorAccess`를 분리한다.
- `SignInLocalDevelopmentAccess`는 브라우저 기반 임시 CLI 인증을 계속 사용할 경우 유지한다.

### 12:58 KST · 비용·S3·최소 권한 구성

- 기존 `My Zero-Spend Budget`의 실제 비용 `$0.01` 초과 알림과 이메일 구독자 1명 확인
- 월 `$5` Budget `VOC-QA-Monthly-5USD` 생성
- 월 Budget 알림: 실제 80%, 실제 100%, 예상 100%
- 기존 S3 버킷 3개는 변경하지 않고 전용 버킷 `voc-qa-evidence-johnna-20693005` 생성
- S3 리전: `ap-northeast-2`
- Public Access Block 4개 항목 활성화
- Object Ownership: `BucketOwnerEnforced`, ACL 비활성화
- 기본 암호화: SSE-S3 `AES256`
- 버전 관리 활성화
- Lifecycle: 현재 객체 90일, 이전 버전 30일, 미완료 멀티파트 업로드 7일
- TLS가 아닌 요청을 거부하는 버킷 정책 적용
- 프로젝트 태그 적용
- IAM 정책 `VOC-QA-EvidenceOperator` 생성·연결
- `AWSBillingReadOnlyAccess`, `AWSCloudShellFullAccess` 연결
- 임시 `AdministratorAccess` 제거
- 13일간 미사용된 장기 Access Key 1개를 삭제하지 않고 `Inactive`로 전환

검증:

- 익명 S3 접근: HTTP 403
- 버킷 정책 공개 상태: false
- AWS Access Analyzer 정책 검증: finding 0건
- 최소 권한 상태에서 사전 점검, 업로드, 다운로드, Budget 조회, CloudTrail 조회 성공
- CloudTrail 관리 이벤트 7종에서 실행 주체 `JohnNa-QA` 확인
- 업로드 Run: `RUN-20260716-110130-319110-c8fe`
- 업로드 객체: 판정 JSON, 판정 Markdown, manifest 총 3개
- 원격 manifest·JSON·Markdown SHA-256: 로컬과 일치
- Free Tier Usage API 조회: 성공, 추적 항목 5개, 최대 사용률 0.01%
- 작업 종료 후 `aws logout --profile JohnNa-QA` 실행, 로컬 로그인 캐시 파일 0개 확인

주의:

- `PutObject`, `DeleteObject`는 S3 데이터 이벤트이므로 기본 CloudTrail Event history에는 나타나지 않는다.
- AWS Budgets는 하드 비용 한도가 아니며 알림이 지연될 수 있다.
- 비활성 Access Key의 기존 사용처가 확인될 때까지 키 자체는 삭제하지 않는다.

### 13:07 KST · 권한 유효기간과 다른 컴퓨터 로그인 검증

- AWS에 등록된 정확한 IAM 사용자명은 `JohnNa-QA`, 계정 별칭은 `johnna-qa`임을 확인
- 콘솔 로그인 프로필과 MFA 장치 1개 활성 상태 확인
- 활성 장기 Access Key 0개, 비활성 장기 Access Key 1개 확인
- 직접 연결 정책 5개와 그룹 `JohnNa-QA`의 `SupportUser` 정책 확인
- `AdministratorAccess` 없음과 Permissions boundary 없음 확인
- 연결 정책에 IP, VPC, 기기 또는 날짜 기반 제한 조건이 없음을 확인
- 사용자 지정 계정 비밀번호 정책이 없어 AWS 기본 정책과 비밀번호 비만료가 적용됨을 확인
- 다른 Windows 컴퓨터용 `tools/aws/00-setup-workstation.ps1` 추가

유효기간:

- IAM 정책 권한은 자동 만료되지 않고 관리자가 변경할 때까지 유지된다.
- MFA는 비활성화 또는 제거할 때까지 유지된다.
- `aws login` 임시 세션은 최대 12시간까지 갱신되며 이후 재인증한다.
- 다른 컴퓨터에서도 동일한 콘솔 비밀번호와 MFA로 독립 로그인할 수 있다.

주의:

- 그룹의 `SupportUser`는 VOC 증적 업무보다 넓은 다수 서비스 조회·진단 및 AWS Support 업무 권한을 포함한다.
- 새 컴퓨터로 `.aws` 폴더, 로그인 캐시, 쿠키 또는 세션 파일을 복사하지 않는다.
