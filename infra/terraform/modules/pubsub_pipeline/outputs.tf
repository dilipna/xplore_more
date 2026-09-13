output "topic_id" {
  value = google_pubsub_topic.main.id
}

output "topic_name" {
  value = google_pubsub_topic.main.name
}

output "subscription_name" {
  value = google_pubsub_subscription.main.name
}

output "dlq_topic_name" {
  value = google_pubsub_topic.dlq.name
}
