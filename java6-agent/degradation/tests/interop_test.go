// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

package opamp

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	pb "github.com/open-telemetry/opamp-go/protobufs"
	"google.golang.org/protobuf/proto"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

func TestPackagedAgentStopResume(t *testing.T) {
	runPackagedAgent(t, true)
}

func TestPackagedAgentWithoutEndpoint(t *testing.T) {
	runPackagedAgent(t, false)
}

func runPackagedAgent(t *testing.T, controlled bool) {
	t.Helper()
	db, err := gorm.Open(sqlite.Open(filepath.Join(t.TempDir(), "opamp.db")), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
	if err != nil {
		t.Fatal(err)
	}
	if err := db.AutoMigrate(&Rule{}, &Instance{}); err != nil {
		t.Fatal(err)
	}
	sql, _ := db.DB()
	defer sql.Close()
	paused := false
	var work, traces, metrics, logs, polls, recording, disabled atomic.Int64
	var dropAck, offline, invalid atomic.Bool
	var dropped, unavailable, rejected atomic.Int64
	var throttle, requestFull, serverUnavailable atomic.Bool
	var throttledAt, retriedAt, fullReports, protocolRetries atomic.Int64
	var dropHash, lastAck atomic.Value
	dropHash.Store("")
	lastAck.Store("")
	badHash := sha256.Sum256([]byte("invalid configuration"))
	mux := http.NewServeMux()
	mux.HandleFunc("/v1/opamp", func(w http.ResponseWriter, r *http.Request) {
		polls.Add(1)
		if r.Header.Get("Authorization") != "" {
			t.Error("probe must connect without an Authorization header")
		}

		body, _ := io.ReadAll(r.Body)
		r.Body = io.NopCloser(bytes.NewReader(body))
		var request pb.AgentToServer
		if err := proto.Unmarshal(body, &request); err != nil {
			t.Error(err)
			w.WriteHeader(400)
			return
		}
		if at := throttledAt.Load(); at > 0 && retriedAt.Load() == 0 {
			retriedAt.Store(time.Now().UnixNano())
		}
		if throttle.CompareAndSwap(true, false) {
			throttledAt.Store(time.Now().UnixNano())
			w.Header().Set("Retry-After", "1")
			w.WriteHeader(429)
			return
		}
		if requestFull.CompareAndSwap(true, false) {
			Handler{db}.ServeHTTP(httptest.NewRecorder(), r)
			body, _ := proto.Marshal(&pb.ServerToAgent{InstanceUid: request.InstanceUid, Flags: uint64(pb.ServerToAgentFlags_ServerToAgentFlags_ReportFullState)})
			w.Header().Set("Content-Type", "application/x-protobuf")
			w.Write(body)
			return
		}
		if retriedAt.Load() > 0 && request.AgentDescription != nil {
			fullReports.Add(1)
		}
		if serverUnavailable.CompareAndSwap(true, false) {
			protocolRetries.Add(1)
			body, _ := proto.Marshal(&pb.ServerToAgent{InstanceUid: request.InstanceUid,
				ErrorResponse: &pb.ServerErrorResponse{Type: pb.ServerErrorResponseType_ServerErrorResponseType_Unavailable,
					Details: &pb.ServerErrorResponse_RetryInfo{RetryInfo: &pb.RetryInfo{RetryAfterNanoseconds: uint64(time.Second)}}}})
			w.Header().Set("Content-Type", "application/x-protobuf")
			w.Write(body)
			return
		}
		ack := request.GetRemoteConfigStatus()
		if ack != nil {
			lastAck.Store(hex.EncodeToString(ack.LastRemoteConfigHash))
			if len(ack.LastRemoteConfigHash) == 0 && ack.Status == pb.RemoteConfigStatuses_RemoteConfigStatuses_FAILED {
				rejected.Add(1)
			}
			if hex.EncodeToString(ack.LastRemoteConfigHash) == dropHash.Load().(string) && dropAck.CompareAndSwap(true, false) {
				dropped.Add(1)
				conn, _, err := w.(http.Hijacker).Hijack()
				if err == nil {
					conn.Close()
				}
				return
			}
		}
		if offline.Load() {
			unavailable.Add(1)
			w.WriteHeader(503)
			return
		}
		if invalid.Load() {
			// Preserve the real server's ACK persistence while replacing only its response.
			// Upstream OpAMP compresses unchanged ACKs; bypassing persistence here would
			// incorrectly leave an old APPLIED status in the database forever.
			Handler{db}.ServeHTTP(httptest.NewRecorder(), r)
			response := &pb.ServerToAgent{InstanceUid: request.InstanceUid, Capabilities: 3, RemoteConfig: &pb.AgentRemoteConfig{ConfigHash: badHash[:], Config: &pb.AgentConfigMap{ConfigMap: map[string]*pb.AgentConfigObject{"elastic": {Body: []byte("{"), ContentType: "application/json"}}}}}
			body, err := proto.Marshal(response)
			if err != nil {
				t.Error(err)
				return
			}
			w.Header().Set("Content-Type", "application/x-protobuf")
			w.Write(body)
			return
		}
		Handler{db}.ServeHTTP(w, r)
	})
	mux.HandleFunc("/work", func(w http.ResponseWriter, r *http.Request) {
		work.Add(1)
		if r.URL.Query().Get("recording") == "true" && r.URL.Query().Get("fresh") == "true" {
			recording.Add(1)
		}
		if r.URL.Query().Get("recording") == "false" && r.URL.Query().Get("fresh") == "false" {
			disabled.Add(1)
		}
		w.Write([]byte("ok"))
	})
	for path, count := range map[string]*atomic.Int64{"/v1/traces": &traces, "/v1/metrics": &metrics, "/v1/logs": &logs} {
		mux.HandleFunc(path, func(w http.ResponseWriter, r *http.Request) {
			n, err := io.Copy(io.Discard, r.Body)
			if err == nil && n > 0 {
				count.Add(1)
			}
			w.Header().Set("Content-Type", "application/x-protobuf")
		})
	}
	server := httptest.NewServer(mux)
	defer server.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 240*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, os.Getenv("INTEROP_JAVA"), "-Xverify:all", "-javaagent:"+os.Getenv("INTEROP_AGENT"),
		"-Dotel.javaagent.opamp.endpoint="+server.URL,
		"-Dotel.service.name=interop", "-Dotel.resource.attributes=deployment.environment=prod",
		"-Dotel.exporter.otlp.endpoint="+server.URL, "-Dotel.exporter.otlp.protocol=http/protobuf",
		"-Dotel.metrics.exporter=otlp", "-Dotel.logs.exporter=otlp", "-Dotel.traces.exporter=otlp",
		"-Dotel.bsp.schedule.delay=200", "-Dotel.blrp.schedule.delay=200", "-Dotel.metric.export.interval=200",
		"-cp", os.Getenv("INTEROP_CLASSPATH"), "io.opentelemetry.javaagent.degradation.InteropApplication", server.URL+"/work")
	if !controlled {
		var args []string
		for _, arg := range cmd.Args {
			if !strings.HasPrefix(arg, "-Delastic.otel.opamp.") && !strings.HasPrefix(arg, "-Dotel.javaagent.opamp.") {
				args = append(args, arg)
			}
		}
		cmd.Args = args
	}
	for _, e := range os.Environ() {
		if !strings.HasPrefix(e, "OTEL_") && !strings.HasPrefix(e, "ELASTIC_OTEL_") && !strings.HasPrefix(e, "JAVA_TOOL_OPTIONS=") && !strings.HasPrefix(e, "JDK_JAVA_OPTIONS=") && !strings.HasPrefix(e, "_JAVA_OPTIONS=") {
			cmd.Env = append(cmd.Env, e)
		}
	}
	var output bytes.Buffer
	cmd.Stdout, cmd.Stderr = &output, &output
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() {
		cancel()
		cmd.Wait()
		t.Log(output.String())
	}()
	wait := func(label string, condition func() bool) {
		t.Helper()
		deadline := time.Now().Add(45 * time.Second)
		for time.Now().Before(deadline) {
			if condition() {
				return
			}
			time.Sleep(100 * time.Millisecond)
		}
		t.Fatalf("timed out: %s; exports=%d/%d/%d work=%d", label, traces.Load(), metrics.Load(), logs.Load(), work.Load())
	}
	if !controlled {
		wait("default-off business and all signals", func() bool {
			return work.Load() > 0 && traces.Load() > 0 && metrics.Load() > 0 && logs.Load() > 0
		})
		time.Sleep(time.Second)
		if polls.Load() != 0 {
			t.Fatalf("unexpected OpAMP requests: %d", polls.Load())
		}
		t.Logf("PASS: default-off; business=%d; trace/metric/log exports=%d/%d/%d; OpAMP requests=0", work.Load(), traces.Load(), metrics.Load(), logs.Load())
		return
	}
	applied := func() bool {
		_, hash := Config(paused)
		var count int64
		db.Model(&Instance{}).Where("service = ? AND ack_hash = ? AND ack_status = 1", "interop", hex.EncodeToString(hash)).Count(&count)
		return count == 1
	}
	wait("initial ACK and all signals", func() bool { return applied() && traces.Load() > 0 && metrics.Load() > 0 && logs.Load() > 0 })
	var instance Instance
	if err := db.First(&instance).Error; err != nil {
		t.Fatal(err)
	}
	if instance.Environment != "prod" {
		t.Fatalf("legacy environment not reported: %q", instance.Environment)
	}
	for cycle, scope := range []string{"service", "instance", "all"} {
		selector := "interop"
		if scope == "instance" {
			selector = instance.UID
		}
		if scope == "all" {
			selector = ""
		}
		paused = true
		if cycle == 0 {
			_, hash := Config(true)
			dropHash.Store(hex.EncodeToString(hash))
			dropAck.Store(true)
		}
		err = SetControl(db, scope, selector, paused, "test")
		if err != nil {
			t.Fatal(err)
		}
		wait("stop ACK", applied)
		if cycle == 0 {
			if dropped.Load() == 0 {
				t.Fatal("ACK transport failure was not exercised")
			}
			offline.Store(true)
			wait("HTTP outage", func() bool { return unavailable.Load() > 0 })
			offline.Store(false)
			invalid.Store(true)
			wait("invalid config rejected", func() bool { return rejected.Load() > 0 })
		}
		time.Sleep(time.Second) // allow exports already in flight before the ACK to drain
		before := [3]int64{traces.Load(), metrics.Load(), logs.Load()}
		beforeWork := work.Load()
		beforeRecording, beforeDisabled := recording.Load(), disabled.Load()
		time.Sleep(2 * time.Second)
		after := [3]int64{traces.Load(), metrics.Load(), logs.Load()}
		if after != before {
			t.Fatalf("signals still exporting: %v -> %v", before, after)
		}
		if recording.Load() != beforeRecording || disabled.Load() <= beforeDisabled {
			t.Fatal("cached/new tracers did not deactivate")
		}
		if work.Load() <= beforeWork {
			t.Fatal("business requests stopped")
		}
		if cycle == 0 {
			invalid.Store(false)
			_, hash := Config(paused)
			wait("valid ACK restored after invalid config", func() bool { return lastAck.Load().(string) == hex.EncodeToString(hash) })
		}
		if cycle == 0 {
			// Resuming all must not clear the service or instance stop rules.
			for _, control := range []struct {
				scope, selector string
				stop            bool
			}{
				{"instance", instance.UID, true}, {"all", "", true}, {"all", "", false}, {"service", "interop", false},
			} {
				if err := SetControl(db, control.scope, control.selector, control.stop, "test"); err != nil {
					t.Fatal(err)
				}
			}
			beforePolls := polls.Load()
			wait("poll after overlapping rule removal", func() bool { return polls.Load() > beforePolls })
			time.Sleep(time.Second)
			if recording.Load() != beforeRecording || traces.Load() != before[0] || metrics.Load() != before[1] || logs.Load() != before[2] {
				t.Fatal("global/service resume incorrectly cleared instance stop")
			}
			if err := SetControl(db, "instance", instance.UID, false, "test"); err != nil {
				t.Fatal(err)
			}
		}
		paused = false
		err = SetControl(db, scope, selector, paused, "test")
		if err != nil {
			t.Fatal(err)
		}
		wait("resume ACK and all signals", func() bool {
			return recording.Load() > beforeRecording && applied() && traces.Load() > before[0] && metrics.Load() > before[1] && logs.Load() > before[2]
		})
	}
	throttle.Store(true)
	wait("HTTP 429 Retry-After", func() bool { return retriedAt.Load() > 0 })
	gap := time.Duration(retriedAt.Load() - throttledAt.Load())
	if gap < 900*time.Millisecond || gap > 10*time.Second {
		t.Fatalf("Retry-After not honored: %s", gap)
	}
	requestFull.Store(true)
	wait("ReportFullState", func() bool { return fullReports.Load() > 0 })
	serverUnavailable.Store(true)
	wait("protocol Unavailable", func() bool { return protocolRetries.Load() > 0 })
	beforePolls := polls.Load()
	wait("protocol retry recovers", func() bool { return polls.Load() > beforePolls })
	var instances int64
	db.Model(&Instance{}).Count(&instances)
	if instances != 1 {
		t.Fatalf("expected one instance, got %d", instances)
	}
	t.Logf("PASS: service/instance/all stop-resume, overlapping rule inheritance, full state, HTTP 429 and protocol retry, dropped ACK retry, HTTP outage, invalid config retained; JVM pid=%d; business=%d; trace/metric/log exports=%d/%d/%d; config ACK applied", cmd.Process.Pid, work.Load(), traces.Load(), metrics.Load(), logs.Load())
}
