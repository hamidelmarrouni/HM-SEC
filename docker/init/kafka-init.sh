#!/bin/sh
set -eu

KAFKA_TOPICS="
user.password-recovery-request.events
user.signup.events
user.profile.events
friendship.events
post.create.events
post.updated.events
post.deleted.events
comment.created.events
comment.delted.events
comment.like.request
comment.unlike.request
comment.liked.events
comment.unliked.events
comment.liked.by.post.author.events
moderation.events
moderation.retry.events
reward.events
message.events
message.special.events
"

echo "[kafka-init] waiting for kafka:9092"
i=0
until /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --list >/dev/null 2>&1; do
  i=$((i+1))
  [ "$i" -ge 90 ] && { echo "[kafka-init] ERROR: Kafka did not become ready" >&2; exit 1; }
  sleep 2
done

echo "[kafka-init] creating required HM_SEC topics"
for topic in $KAFKA_TOPICS; do
  /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server kafka:9092 \
    --create --if-not-exists \
    --topic "$topic" --partitions 1 --replication-factor 1 >/dev/null
done

echo "[kafka-init] topics ready"
