"""Alert engine (Phase 3 deliverable).

High-impact changes raise an alert immediately; Medium ones are logged for the weekly digest.
Alerts always go to data/<store>/alerts.jsonl. If SNS_TOPIC_ARN and/or ALERT_WEBHOOK_URL are set
they are also pushed out (email/SMS via SNS, Teams/Slack via webhook).

`alert_type` is generic so other modules (price changes, promotions, partnerships) can write
to the same stream later.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

import config


def build_alert(record: dict) -> dict:
    eff = record.get("effective_date")
    return {
        "alert_id": f"visa-{record['id']}",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "alert_type": "government_visa_announcement",
        "severity": record["impact"],
        "title": record["title"],
        "message": (
            f"[{record['impact']}] {record['title']}\n"
            f"Visas: {', '.join(record['visa_categories']) or 'n/a'} | "
            f"Products: {', '.join(record['products_affected']) or 'n/a'}\n"
            f"Effective: {eff or 'not stated'}\n"
            f"Why: {record['impact_rationale']}\n"
            f"Source: {record['url']}"
        ),
        "url": record["url"],
        "effective_date": eff,
        "record_id": record["id"],
    }


def _notify(alert: dict) -> None:
    if config.SNS_TOPIC_ARN:
        import boto3

        boto3.client("sns", region_name=config.REGION).publish(
            TopicArn=config.SNS_TOPIC_ARN,
            Subject=f"Visa alert: {alert['title']}"[:100],
            Message=alert["message"],
        )
    if config.ALERT_WEBHOOK_URL:
        requests.post(config.ALERT_WEBHOOK_URL, json={"text": alert["message"]}, timeout=15)


def process(new_records: list[dict], root: Path, notify: bool = True) -> list[dict]:
    """Create alerts for new High/Medium records. Only High ones are pushed out."""
    alerts = [build_alert(r) for r in new_records if r["impact"] in ("High", "Medium")]
    if not alerts:
        return []
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "alerts.jsonl", "a", encoding="utf-8") as fh:
        for a in alerts:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")
    if notify:
        for a in alerts:
            if a["severity"] == "High":
                try:
                    _notify(a)
                except Exception as e:  # noqa: BLE001 - never lose the run over a notification
                    print(f"  alert delivery failed for {a['alert_id']}: {e}")
    return alerts


def load_alerts(root: Path) -> list[dict]:
    f = root / "alerts.jsonl"
    if not f.exists():
        return []
    with open(f, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return sorted(rows, key=lambda a: a["created_at"], reverse=True)
