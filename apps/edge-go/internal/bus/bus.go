// Package bus publishes events. Production uses Pub/Sub; tests use Memory.
package bus

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"

	"cloud.google.com/go/pubsub/v2"
)

// Publisher sends one message and blocks until the server acknowledges it.
type Publisher interface {
	Publish(ctx context.Context, topic string, data []byte, attrs map[string]string) error
	Close() error
}

// PublishJSON marshals v and publishes it with its event type as an attribute, which lets
// subscriptions filter by type without parsing bodies.
func PublishJSON(ctx context.Context, p Publisher, topic, eventType string, v any) error {
	data, err := json.Marshal(v)
	if err != nil {
		return fmt.Errorf("marshal event: %w", err)
	}
	return p.Publish(ctx, topic, data, map[string]string{"type": eventType})
}

// PubSub publishes to Google Cloud Pub/Sub (or the emulator via PUBSUB_EMULATOR_HOST).
type PubSub struct {
	client *pubsub.Client
	mu     sync.Mutex
	topics map[string]*pubsub.Publisher
}

// NewPubSub connects to project.
func NewPubSub(ctx context.Context, project string) (*PubSub, error) {
	client, err := pubsub.NewClient(ctx, project)
	if err != nil {
		return nil, fmt.Errorf("pubsub client: %w", err)
	}
	return &PubSub{client: client, topics: map[string]*pubsub.Publisher{}}, nil
}

func (p *PubSub) publisher(topic string) *pubsub.Publisher {
	p.mu.Lock()
	defer p.mu.Unlock()
	pub, ok := p.topics[topic]
	if !ok {
		pub = p.client.Publisher(topic)
		p.topics[topic] = pub
	}
	return pub
}

// Publish waits for the server ack, so a successful return means the event is durable
// before the caller acknowledges its own input (no silent loss on crash).
func (p *PubSub) Publish(ctx context.Context, topic string, data []byte, attrs map[string]string) error {
	result := p.publisher(topic).Publish(ctx, &pubsub.Message{Data: data, Attributes: attrs})
	if _, err := result.Get(ctx); err != nil {
		return fmt.Errorf("publish to %s: %w", topic, err)
	}
	return nil
}

// Close flushes pending batches and releases connections.
func (p *PubSub) Close() error {
	p.mu.Lock()
	for _, pub := range p.topics {
		pub.Stop()
	}
	p.mu.Unlock()
	return p.client.Close()
}

// Message is a captured publish for tests.
type Message struct {
	Topic string
	Data  []byte
	Attrs map[string]string
}

// Memory records publishes in order. Safe for concurrent use.
type Memory struct {
	mu       sync.Mutex
	Messages []Message
	Err      error // if set, Publish fails with it
}

func (m *Memory) Publish(_ context.Context, topic string, data []byte, attrs map[string]string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.Err != nil {
		return m.Err
	}
	m.Messages = append(m.Messages, Message{Topic: topic, Data: append([]byte(nil), data...), Attrs: attrs})
	return nil
}

func (m *Memory) Close() error { return nil }

// Snapshot returns a copy of recorded messages.
func (m *Memory) Snapshot() []Message {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]Message(nil), m.Messages...)
}
