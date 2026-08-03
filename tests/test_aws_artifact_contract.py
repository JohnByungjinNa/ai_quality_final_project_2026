import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "aws"
TOOLS = ROOT / "tools" / "aws"
BUCKET = "voc-qa-evidence-johnna-20693005"


def test_bucket_policy_blocks_insecure_transport():
    policy = json.loads((CONFIG / "voc-qa-bucket-policy.json").read_text(encoding="utf-8"))
    statement = policy["Statement"][0]

    assert statement["Effect"] == "Deny"
    assert statement["Condition"]["Bool"]["aws:SecureTransport"] == "false"
    assert f"arn:aws:s3:::{BUCKET}" in statement["Resource"]


def test_lifecycle_limits_current_and_noncurrent_evidence():
    lifecycle = json.loads((CONFIG / "voc-qa-lifecycle.json").read_text(encoding="utf-8"))
    rule = lifecycle["Rules"][0]

    assert rule["Status"] == "Enabled"
    assert rule["Filter"]["Prefix"] == "voc-quality-runs/"
    assert rule["Expiration"]["Days"] == 90
    assert rule["NoncurrentVersionExpiration"]["NoncurrentDays"] == 30
    assert rule["AbortIncompleteMultipartUpload"]["DaysAfterInitiation"] == 7


def test_operator_policy_cannot_delete_or_administer_bucket():
    policy = json.loads((CONFIG / "voc-qa-operator-policy.json").read_text(encoding="utf-8"))
    actions = {
        action
        for statement in policy["Statement"]
        for action in ([statement["Action"]] if isinstance(statement["Action"], str) else statement["Action"])
    }

    assert "s3:PutObject" in actions
    assert "s3:GetObject" in actions
    assert "cloudtrail:LookupEvents" in actions
    assert "s3:DeleteObject" not in actions
    assert "s3:DeleteBucket" not in actions
    assert "s3:PutBucketPolicy" not in actions


def test_upload_script_limits_files_and_scans_secrets():
    source = (TOOLS / "03-upload-run-evidence.ps1").read_text(encoding="utf-8")

    assert '"step10_acceptance.json", "step10_acceptance.md"' in source
    assert "5MB" in source
    assert "PRIVATE KEY" in source
    assert "aws_s3_manifest.json" in source


def test_workstation_setup_uses_browser_login_without_access_keys():
    source = (TOOLS / "00-setup-workstation.ps1").read_text(encoding="utf-8")

    assert "AWSCLIV2-User.msi" in source
    assert "awscli.amazonaws.com" in source
    assert "login --profile" in source
    assert "get-caller-identity" in source
    assert "JohnNa-QA" in source
    assert "create-access-key" not in source
