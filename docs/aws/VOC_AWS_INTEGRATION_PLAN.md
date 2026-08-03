# VOC 품질진단 AWS 연동 계획

## 1. 목표와 범위

첫 AWS 연동 범위는 애플리케이션 배포가 아니라 다음 운영 기반 구축으로 제한한다.

- 사람별 AWS 로그인과 최소 권한 분리
- 비용 발생 전후 알림과 일일 비용 확인 절차
- CloudShell 기반의 재현 가능한 AWS CLI 실행
- VOC 품질 보고서와 증적 파일의 비공개 S3 보관
- 버킷 관리 이벤트와 업로드 결과 검증

EC2, RDS, Lambda, CloudFront와 상시 실행 워크로드는 이번 범위에서 제외한다.

## 2. 기본 설계안

| 항목 | 기본안 | 이유 |
| --- | --- | --- |
| 리전 | `ap-northeast-2` | 팀이 하나의 리전에서 작업하고 CloudTrail 조회 범위를 단순화한다. |
| 사람 로그인 | 기존 IAM 사용자 `JohnNa-QA` + MFA + `aws login` 임시 자격 증명 | 단일 실습 계정에서 Organizations 생성 없이 루트와 장기 Access Key 사용을 피한다. |
| 루트 사용자 | MFA 활성화, Access Key 미생성, 일상 작업 금지 | 계정 복구·결제 등 루트 전용 작업에만 사용한다. |
| S3 공개 범위 | 모든 Public Access Block 활성화 | 품질 보고서와 증적은 외부 공개 대상이 아니다. |
| S3 소유권 | Bucket owner enforced, ACL 비활성화 | 접근 제어를 IAM·버킷 정책으로 단일화한다. |
| S3 암호화 | 기본 SSE-S3 | 별도 KMS 요청 비용과 키 운영 부담을 만들지 않는다. |
| S3 버전 관리 | 활성화 제안 | 실수로 덮어쓴 증적을 복구할 수 있게 한다. |
| 수명 주기 | 비현재 버전 30일, 전체 Run 증적 90일 보관 후 만료 제안 | 교육·시연 범위의 복구성과 비용을 절충한다. 실제 보존 기간은 생성 전에 확정한다. |
| 비용 알림 | Zero Spend Budget + 월 소액 예산 | 무료 한도 초과와 월 누적 비용을 각각 감시한다. |
| CloudTrail | 기본 Event history, S3 데이터 이벤트는 초기 비활성화 | 관리 이벤트의 최근 90일 조회는 무료지만 객체 이벤트는 별도 과금 가능성이 있다. |

새 AWS 계정은 Free plan과 Paid plan의 조건이 다르므로 계정 생성 시 선택한 플랜과 크레딧 만료일을 먼저 확인한다. Free plan 계정을 AWS Organizations에 가입시키면 플랜과 크레딧 조건이 바뀔 수 있으므로 이번 실습에서는 Organizations를 사용하지 않는다. IAM Identity Center의 계정 인스턴스는 AWS 계정 접근과 Permission Set을 지원하지 않으므로 현재 단일 계정에서는 기존 IAM 사용자와 브라우저 기반 임시 CLI 인증을 사용한다. 다중 계정 운영으로 전환할 때 조직 인스턴스 도입을 재검토한다.

## 3. 권한 역할

| 역할 | 대상 | 허용 범위 |
| --- | --- | --- |
| `AWS-Lab-Admin` | 최초 설정 담당자 1~2명 | IAM Identity Center, Budgets, 대상 S3 버킷 설정과 검증 |
| `VOC-QA-Uploader` | 보고서 업로드 담당자 | 대상 버킷·접두사에 대한 목록, 업로드, 다운로드. 버킷 생성·정책 변경·객체 삭제 제외 |
| `VOC-QA-Auditor` | 검토자 | 대상 버킷과 객체 읽기, 버킷 설정 읽기, CloudTrail `LookupEvents`, 비용 화면 읽기 |

권한은 특정 버킷 ARN과 아래 접두사로 제한한다.

```text
s3://<bucket-name>/voc-quality-runs/<RUN_ID>/
├─ reports/
├─ evidence/
└─ manifest.json
```

팀원에게 IAM 사용자의 장기 Access Key를 발급하지 않는다. 로컬 자동화가 나중에 필요하면 IAM Identity Center의 AWS CLI SSO 또는 워크로드용 IAM Role을 별도 설계한다.

## 4. 단계별 진행 절차

### Phase 0. 사전 결정

확정할 값:

- AWS 계정 플랜과 Free Tier·크레딧 상태
- 알림 수신 이메일
- 월 예산 상한의 USD 금액
- 리전
- S3 증적 보존 기간
- 팀원과 `Admin`, `Uploader`, `Auditor` 역할 매핑

완료 기준:

- 루트 MFA가 활성화되어 있다.
- 루트 Access Key가 없다.
- 계정 ID, 이메일, 비밀값을 저장소에 기록하지 않는 원칙에 동의한다.

### Phase 1. 비용 안전장치

1. Billing preferences에서 Free Tier 사용량 이메일 알림을 활성화한다.
2. Zero Spend Budget을 만든다.
3. 월 소액 Cost Budget을 만들고 실제 비용 임계값을 설정한다.
4. 알림 이메일의 구독·수신 여부를 확인한다.
5. Billing 홈에서 현재 플랜, 크레딧, 이번 달 비용을 캡처한다.

주의:

- AWS Budgets는 하드 사용 한도가 아니다.
- 비용 데이터와 알림은 지연될 수 있으므로 리소스를 즉시 중단한다고 가정하지 않는다.
- 첫 단계에서는 자동 Budget Action을 적용하지 않고 알림만 사용한다.

완료 기준:

- 두 Budget이 `OK` 또는 정상 감시 상태다.
- 알림 대상이 검증되었다.
- 일일 비용 확인 담당자가 지정되었다.

### Phase 2. 로그인과 최소 권한

1. IAM Identity Center를 활성화하고 팀원별 사용자를 만든다.
2. `AWS-Lab-Admin`, `VOC-QA-Uploader`, `VOC-QA-Auditor` Permission Set을 만든다.
3. MFA와 임시 세션 로그인을 확인한다.
4. 역할별 허용·차단 테스트를 수행한다.

최소 권한 검증 예:

- Uploader: 지정 접두사 업로드 성공
- Uploader: 버킷 삭제, 정책 변경, 객체 공개 설정 실패
- Auditor: 객체·설정 조회 성공, 업로드·삭제 실패

완료 기준:

- 공용 계정과 장기 Access Key 없이 세 역할로 로그인할 수 있다.
- 의도한 허용 작업과 차단 작업의 CLI 결과가 보존되었다.

### Phase 3. S3 증적 저장소 구축

1. 전역에서 유일한 버킷 이름을 확정한다.
2. 지정 리전에 버킷을 만든다.
3. Public Access Block 4개 항목, ACL 비활성화, SSE-S3를 확인한다.
4. 버전 관리와 합의한 Lifecycle을 적용한다.
5. TLS가 아닌 요청을 거부하는 버킷 정책을 적용한다.
6. 프로젝트 태그를 적용한다.

권장 태그:

```text
Project=VOC-Quality
Environment=training
Owner=<team-name>
ManagedBy=aws-cli
```

완료 기준:

- 공개 접근이 차단된다.
- 암호화, 버전 관리, Lifecycle, 태그가 CLI 조회 결과와 일치한다.
- 허용되지 않은 사용자와 공개 URL로 객체를 읽을 수 없다.

### Phase 4. 보고서·증적 업로드 연동

초기에는 VOC 화면에 AWS 자격 증명을 입력하는 기능을 만들지 않는다. CloudShell에서 선택 Run의 필요한 파일만 업로드한다.

대상 예:

```text
reports/voc_quality_runs/<RUN_ID>/evidence/step10_acceptance.json
reports/voc_quality_runs/<RUN_ID>/evidence/step10_acceptance.md
```

업로드 절차:

1. 파일 존재, 크기, SHA-256을 확인한다.
2. 허용된 확장자와 크기 제한을 통과한 파일만 업로드한다.
3. `RUN_ID`, 생성 시각, 로컬 SHA-256, S3 Key를 `manifest.json`에 기록한다.
4. `head-object`로 객체 크기, 암호화, 메타데이터를 재확인한다.
5. 동일 Run 재업로드 시 버전 ID와 해시를 비교한다.

완료 기준:

- 보고서·증적·manifest만 업로드된다.
- 로컬과 S3의 파일 크기·SHA-256이 일치한다.
- 애플리케이션과 저장소 어디에도 AWS 비밀값이 남지 않는다.

### Phase 5. CloudTrail 감사 확인

기본 Event history에서 다음 관리 이벤트를 확인한다.

- `CreateBucket`
- `PutBucketPublicAccessBlock`
- `PutBucketEncryption`
- `PutBucketVersioning`
- `PutLifecycleConfiguration`
- `PutBucketPolicy`

`PutObject`와 `DeleteObject`는 S3 데이터 이벤트이므로 무료 Event history의 관리 이벤트만으로 확인할 수 없다. 초기에는 다음으로 업로드를 검증한다.

- AWS CLI 명령 결과
- `head-object`
- `list-object-versions`
- 로컬/S3 SHA-256 비교 manifest

평가 요건상 객체 API 감사가 반드시 필요하면 대상 버킷과 접두사에만 S3 데이터 이벤트를 활성화하고 예상 이벤트 수와 비용을 확인한 후 별도 승인한다.

완료 기준:

- 버킷 설정 변경 주체·시각·리전이 CloudTrail에서 확인된다.
- 업로드 객체가 manifest 및 S3 조회 결과와 일치한다.
- 데이터 이벤트 사용 여부와 비용 영향이 명시되어 있다.

### Phase 6. Billing·Free Tier 일일 점검

실습 기간 동안 매일 다음을 확인한다.

- Billing 홈의 월 누적 예상 비용
- Free Tier 또는 크레딧 잔액과 만료일
- Budgets 상태와 알림 이력
- S3 저장 용량, 객체 수, 요청 증가 원인
- 예상하지 않은 리전 또는 서비스 비용

완료 기준:

- 일일 점검표에 날짜, 확인자, 비용, 이상 여부가 기록된다.
- 예상하지 않은 비용이 있으면 신규 리소스 생성을 중단하고 원인을 먼저 확인한다.

### Phase 7. UAT와 종료

UAT 시나리오:

1. Uploader가 한 Run의 증적을 업로드한다.
2. Auditor가 다운로드하고 해시를 검증한다.
3. Uploader의 정책 변경·삭제가 거부되는지 확인한다.
4. Admin이 버킷 관리 이벤트를 CloudTrail에서 찾는다.
5. Budgets와 Billing에서 비용 상태를 확인한다.

종료 또는 정리 시에는 먼저 대상 버킷·객체·버전을 정확히 나열하고 사용자 승인을 받은 뒤 수행한다. 증적 보존이 필요하면 객체를 삭제하지 않고 업로드 권한만 제거한다.

## 5. 저장소 구현 산출물

다음 구현 단계에서 아래 파일을 추가한다.

```text
config/aws/voc-qa.env.example
config/aws/voc-qa-uploader-policy.json
config/aws/voc-qa-auditor-policy.json
tools/aws/01-preflight.ps1
tools/aws/02-create-s3.ps1
tools/aws/03-upload-run-evidence.ps1
tools/aws/04-verify-evidence.ps1
tools/aws/05-audit-events.ps1
docs/aws/VOC_AWS_OPERATIONS_GUIDE.md
tests/test_aws_artifact_contract.py
```

실제 계정 ID, 이메일, 버킷 이름, 자격 증명은 커밋하지 않는다. 예제 설정에는 자리표시자만 둔다.

## 6. 권장 진행 순서

1. Phase 0의 계정·예산·보존 기간을 사용자와 확정한다.
2. 비용 알림을 가장 먼저 만든다.
3. Identity Center와 역할을 구성한다.
4. 저장소에 정책·CloudShell 스크립트·테스트를 구현한다.
5. 사용자 확인 후 실제 S3 버킷을 생성한다.
6. 한 개 Run으로 업로드·감사·비용 UAT를 수행한다.
7. UAT 통과 후에만 VOC 화면의 선택적 `S3 증적 업로드` 기능을 검토한다.

VOC 화면 직접 연동은 AWS 기본 구성이 검증되기 전에는 구현하지 않는다. 이렇게 하면 애플리케이션에 장기 자격 증명을 넣는 설계와 불필요한 AWS 쓰기를 피할 수 있다.
