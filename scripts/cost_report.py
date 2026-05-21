#!/usr/bin/env python3
"""
Weekly cost report — sums costs.jsonl MTD, posts to Slack, alerts if MTD > $5.
Runs every Sunday via cost-report.yml.
"""

from datetime import datetime
from cost_tracker import month_to_date_total
import slack_post

LIMIT = 10.0  # Anthropic Console hard limit
ALERT_THRESHOLD = 5.0


def main():
    month = datetime.now().strftime("%Y-%m")
    mtd = month_to_date_total()
    blocks = slack_post.cost_report_blocks(month, mtd, limit=LIMIT)
    slack_post.post(blocks)
    print(f"💰 {month} MTD: ${mtd:.4f} / ${LIMIT:.2f}")
    if mtd > ALERT_THRESHOLD:
        print(f"🚨 MTD exceeds ${ALERT_THRESHOLD:.2f} alert threshold")


if __name__ == "__main__":
    main()
