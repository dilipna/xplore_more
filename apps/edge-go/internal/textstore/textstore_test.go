package textstore

import (
	"compress/gzip"
	"context"
	"io"
	"os"
	"strings"
	"testing"
	"time"
)

func TestFilePutIsIdempotentAndContentAddressed(t *testing.T) {
	store := File{Dir: t.TempDir()}
	at := time.Date(2026, 9, 13, 10, 0, 0, 0, time.UTC)
	id := strings.Repeat("a", 64)
	hashV1 := strings.Repeat("1", 64)
	hashV2 := strings.Repeat("2", 64)

	uri1, err := store.Put(context.Background(), id, hashV1, "first text", at)
	if err != nil {
		t.Fatal(err)
	}
	again, err := store.Put(context.Background(), id, hashV1, "IGNORED: same key", at)
	if err != nil || again != uri1 {
		t.Fatalf("retry: uri %q err %v", again, err)
	}
	uri2, err := store.Put(context.Background(), id, hashV2, "second text", at)
	if err != nil || uri2 == uri1 {
		t.Fatalf("new content must get a new object: %q %v", uri2, err)
	}
	if got := readGzip(t, uri1); got != "first text" {
		t.Fatalf("original text overwritten: %q", got)
	}
}

func readGzip(t *testing.T, uri string) string {
	t.Helper()
	f, err := os.Open(strings.TrimPrefix(uri, "file://"))
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	gz, err := gzip.NewReader(f)
	if err != nil {
		t.Fatal(err)
	}
	b, _ := io.ReadAll(gz)
	return string(b)
}
