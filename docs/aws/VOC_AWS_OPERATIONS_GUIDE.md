# VOC AWS 운영 가이드

## 다른 컴퓨터에서 처음 사용

저장소를 새 컴퓨터에 받은 뒤 다음 명령을 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/aws/00-setup-workstation.ps1
```

이 스크립트는 공식 AWS CLI v2를 사용자 범위에 설치하고, IAM 로그인 주소를 연 뒤 `aws login` 임시 인증과 호출 주체 검증을 수행한다. IAM 사용자 `JohnNa-QA`, 기존 콘솔 비밀번호와 등록된 MFA를 사용한다.

기존 컴퓨터의 `.aws` 폴더, 로그인 캐시, 쿠키 또는 세션 파일은 복사하지 않는다. 컴퓨터마다 독립적으로 로그인한다.

## 로그인

장기 Access Key 대신 콘솔 자격 증명의 임시 세션을 사용한다.

```powershell
aws login --profile JohnNa-QA --region ap-northeast-2
```

브라우저에서 IAM 사용자 `JohnNa-QA`를 선택한다. 루트 사용자를 선택하면 사전 점검이 실패한다.

CLI 임시 세션은 최대 12시간까지 갱신할 수 있으며 이후 다시 인증한다. IAM에 연결된 정책 권한 자체에는 자동 만료일이 없으므로 관리자가 변경할 때까지 유지된다.

작업 종료 시:

```powershell
aws logout --profile JohnNa-QA
```

## 사전 점검

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/aws/01-preflight.ps1
```

호출 주체, 서울 리전, 공개 차단, AES256, 버전 관리와 월 `$5` Budget을 모두 확인한다.

## Run 증적 업로드

먼저 VOC 화면의 `최종 판정 증적 저장`으로 Run 증적을 생성한다. 이후 다음을 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/aws/03-upload-run-evidence.ps1 `
  -RunId RUN-YYYYMMDD-HHMMSS-NNNNNN-xxxx
```

업로드 대상은 다음 세 파일이다.

- `step10_acceptance.json`
- `step10_acceptance.md`
- 스크립트가 생성하는 `aws_s3_manifest.json`

5MB 초과 파일이나 비밀값 후보가 감지된 파일은 업로드하지 않는다.

## 원격 무결성 확인

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/aws/04-verify-evidence.ps1 `
  -RunId RUN-YYYYMMDD-HHMMSS-NNNNNN-xxxx
```

원격 manifest와 증적을 임시 폴더로 내려받아 로컬 SHA-256·크기와 비교하고 임시 파일을 제거한다.

## CloudTrail 관리 이벤트 확인

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/aws/05-audit-events.ps1
```

버킷 생성·암호화·공개 차단·버전·Lifecycle·정책·태그 변경을 확인한다. 객체 업로드·삭제는 S3 데이터 이벤트이므로 기본 90일 Event history에는 나타나지 않는다.

## 비용 확인

매일 AWS Console의 `Billing and Cost Management`에서 다음을 확인한다.

- 이번 달 누적·예상 비용
- `My Zero-Spend Budget`
- `VOC-QA-Monthly-5USD`
- Free Tier 또는 크레딧 잔액과 만료일
- 예상하지 않은 서비스·리전 비용

Budget은 비용을 즉시 차단하지 않는다. 알림이 오면 신규 리소스 생성을 멈추고 원인을 먼저 확인한다.

## 권한 기준

`JohnNa-QA`에는 다음 직접 정책만 유지한다.

- `SignInLocalDevelopmentAccess`
- `VOC-QA-EvidenceOperator`
- `AWSBillingReadOnlyAccess`
- `AWSCloudShellFullAccess`
- 기존 `IAMUserChangePassword`

`AdministratorAccess`는 유지하지 않는다. S3 객체 삭제, 버킷 삭제와 버킷 정책 변경 권한도 부여하지 않는다.

기존 `JohnNa-QA` 그룹의 `SupportUser` 정책은 AWS Support 업무와 여러 서비스의 광범위한 조회·진단 권한을 제공한다. Support 업무가 필요하지 않다면 별도 승인 후 분리 여부를 검토한다.

## 복구·주의

- 기존 장기 Access Key 1개는 미사용 상태에서 `Inactive`로 전환했다. 사용처가 확인될 때까지 삭제하지 않는다.
- 증적 삭제나 버킷 삭제는 별도 승인 후 정확한 객체 버전과 버킷을 확인하고 수행한다.
- 계정 ID, 이메일, Access Key, 세션 토큰은 저장소와 작업 기록에 남기지 않는다.
