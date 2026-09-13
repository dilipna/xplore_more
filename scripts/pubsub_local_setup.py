"""Create the Pub/Sub topology in the local emulator (mirrors infra/terraform/modules/pubsub_pipeline).

Usage (emulator running on localhost:8085):
    PUBSUB_EMULATOR_HOST=localhost:8085 uv run python scripts/pubsub_local_setup.py \
        --push-endpoint http://ingestor:8080/push/article-discovered
"""

from __future__ import annotations

import argparse
import os

from google.api_core.exceptions import AlreadyExists
from google.cloud import pubsub_v1

TOPICS = [
    "article-discovered",
    "article-discovered-dlq",
    "article-extracted",
    "article-extracted-dlq",
    "story-updated",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=os.environ.get("XM_GCP_PROJECT", "xm-local"))
    parser.add_argument("--push-endpoint", default="http://ingestor:8080/push/article-discovered")
    args = parser.parse_args()
    if not os.environ.get("PUBSUB_EMULATOR_HOST"):
        raise SystemExit("refusing to run without PUBSUB_EMULATOR_HOST (this script targets the emulator)")

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    for topic in TOPICS:
        try:
            publisher.create_topic(request={"name": publisher.topic_path(args.project, topic)})
            print(f"topic {topic}")
        except AlreadyExists:
            print(f"topic {topic} (exists)")

    subscriptions = [
        {
            "name": subscriber.subscription_path(args.project, "article-discovered-ingestor"),
            "topic": publisher.topic_path(args.project, "article-discovered"),
            "push_config": {"push_endpoint": args.push_endpoint},
            "ack_deadline_seconds": 90,
            "dead_letter_policy": {
                "dead_letter_topic": publisher.topic_path(args.project, "article-discovered-dlq"),
                "max_delivery_attempts": 5,
            },
        },
        {
            "name": subscriber.subscription_path(args.project, "article-extracted-indexer"),
            "topic": publisher.topic_path(args.project, "article-extracted"),
            "ack_deadline_seconds": 120,
            "dead_letter_policy": {
                "dead_letter_topic": publisher.topic_path(args.project, "article-extracted-dlq"),
                "max_delivery_attempts": 5,
            },
        },
        {
            "name": subscriber.subscription_path(args.project, "article-discovered-dlq-inspect"),
            "topic": publisher.topic_path(args.project, "article-discovered-dlq"),
        },
        {
            "name": subscriber.subscription_path(args.project, "article-extracted-dlq-inspect"),
            "topic": publisher.topic_path(args.project, "article-extracted-dlq"),
        },
    ]
    for sub in subscriptions:
        try:
            subscriber.create_subscription(request=sub)
            print(f"subscription {sub['name'].rsplit('/', 1)[-1]}")
        except AlreadyExists:
            print(f"subscription {sub['name'].rsplit('/', 1)[-1]} (exists)")


if __name__ == "__main__":
    main()
