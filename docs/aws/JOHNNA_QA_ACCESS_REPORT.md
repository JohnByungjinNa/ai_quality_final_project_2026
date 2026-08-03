# JohnNa-QA 권한 및 다중 PC 사용 확인서

확인 일시: 2026-08-03 KST

## 계정과 인증 상태

- IAM 사용자명: `JohnNa-QA` (대소문자 포함 정확한 이름)
- 계정 별칭: `johnna-qa`
- 콘솔 로그인 프로필: 활성
- MFA 장치: 1개 활성
- 활성 장기 Access Key: 0개
- 비활성 장기 Access Key: 1개(기존 사용처 확인 전 보존)
- Permissions boundary: 없음

## 현재 권한 범위

| 경로 | 정책 | 주요 범위 |
| --- | --- | --- |
| 직접 | `IAMUserChangePassword` | 본인 콘솔 비밀번호 변경 |
| 직접 | `SignInLocalDevelopmentAccess` | 콘솔 인증을 이용한 AWS CLI 임시 세션 로그인 |
| 직접 | `AWSCloudShellFullAccess` | CloudShell 환경 사용 |
| 직접 | `AWSBillingReadOnlyAccess` | Billing·비용 정보 읽기 |
| 직접 | `VOC-QA-EvidenceOperator` | 전용 S3 증적 경로 읽기·업로드, CloudTrail 조회, Budget 조회 |
| 그룹 `JohnNa-QA` | `SupportUser` | AWS Support 업무와 다수 AWS 서비스의 광범위한 조회·진단 작업 |

`AdministratorAccess`는 없다. 프로젝트 전용 정책은 S3 객체 삭제, 버킷 삭제, 버킷 정책 변경과 IAM 관리 권한을 허용하지 않는다. 다만 기존 그룹의 `SupportUser`는 VOC 프로젝트 전용 정책보다 범위가 넓으므로, AWS Support 업무가 필요하지 않다면 별도 검토 후 분리하는 것이 최소 권한 원칙에 더 적합하다.

## 권한과 인증의 유효기간

- IAM 정책 권한: 자동 만료 조건이 없다. 관리자에 의해 정책·그룹·사용자가 변경될 때까지 유지된다.
- 콘솔 비밀번호: 계정에 사용자 지정 비밀번호 정책이 없어 AWS 기본 정책이 적용되며 자동 만료되지 않는다.
- MFA: 관리자가 장치를 비활성화하거나 제거할 때까지 유지된다.
- `aws login` CLI 세션: 임시 자격 증명을 약 15분마다 갱신하며, 한 번 인증한 세션은 최대 12시간까지 사용할 수 있다. 이후 다시 브라우저 인증한다.
- IP·VPC·날짜 조건: 현재 연결 정책에서 확인되지 않았다.

## 다른 장소·컴퓨터 사용 가능 여부

가능하다. IAM 사용자는 특정 사무실 PC에 귀속되지 않으며 현재 정책에 접속 IP, VPC 또는 기기 제한이 없다. 새 컴퓨터에서 아래 정보를 사용해 별도로 로그인한다.

- 로그인 주소: `https://johnna-qa.signin.aws.amazon.com/console/`
- IAM 사용자명: `JohnNa-QA`
- 기존 콘솔 비밀번호와 등록된 MFA

저장소를 새 컴퓨터에 받은 뒤 다음 명령을 실행하면 AWS CLI 설치, 브라우저 임시 로그인, 호출 주체 확인과 사전 점검을 순서대로 수행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/aws/00-setup-workstation.ps1
```

기존 PC의 `.aws` 폴더, 로그인 캐시, 쿠키 또는 세션 파일을 복사하지 않는다. 작업 종료 시 `aws logout --profile JohnNa-QA`를 실행한다.
