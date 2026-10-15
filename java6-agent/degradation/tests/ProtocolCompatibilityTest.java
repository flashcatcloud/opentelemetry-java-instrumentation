/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.javaagent.degradation;

import com.google.protobuf.ByteString;
import io.opentelemetry.javaagent.degradation.opampclient.OpampClient;
import io.opentelemetry.javaagent.degradation.opampclient.OpampClientBuilder;
import io.opentelemetry.javaagent.degradation.opampclient.internal.connectivity.http.RetryAfterParser;
import io.opentelemetry.javaagent.degradation.opampclient.internal.request.Request;
import io.opentelemetry.javaagent.degradation.opampclient.internal.request.delay.RetryPeriodicDelay;
import io.opentelemetry.javaagent.degradation.opampclient.internal.response.MessageData;
import io.opentelemetry.javaagent.degradation.opampclient.internal.response.Response;
import io.opentelemetry.javaagent.degradation.opampclient.request.service.RequestService;
import java8.util.function.Supplier;
import opamp.proto.v1.Opamp.*;
import org.threeten.bp.Duration;

/** Runs directly against the backported upstream state machine, without a mock protocol client. */
public final class ProtocolCompatibilityTest {
  private static void check(boolean value, String message) {
    if (!value) throw new AssertionError(message);
  }

  public static void main(String[] args) throws Exception {
    // The normal entry is an interface static method, relocated by Retrolambda on Java 6.
    java.lang.reflect.Constructor<OpampClientBuilder> ctor =
        OpampClientBuilder.class.getDeclaredConstructor();
    ctor.setAccessible(true);
    FakeService service = new FakeService();
    OpampClient client =
        ctor.newInstance()
            .enableRemoteConfig()
            .putIdentifyingAttribute("service.name", "test")
            .setRequestService(service)
            .build(new Callbacks());
    AgentToServer first = service.last;
    check(
        first.getSequenceNum() == 1
            && first.getInstanceUid().size() == 16
            && first.hasAgentDescription(),
        "initial complete state");
    long caps =
        AgentCapabilities.AgentCapabilities_AcceptsRemoteConfig.getNumber()
            | AgentCapabilities.AgentCapabilities_ReportsRemoteConfig.getNumber();
    check(first.getCapabilities() == caps, "advertise only implemented capabilities");
    service.capture();
    check(
        !service.last.hasAgentDescription() && service.last.getSequenceNum() == 2,
        "status compression");
    RemoteConfigStatus ack =
        RemoteConfigStatus.newBuilder()
            .setStatus(RemoteConfigStatuses.RemoteConfigStatuses_APPLIED)
            .setLastRemoteConfigHash(ByteString.copyFromUtf8("hash"))
            .build();
    client.setRemoteConfigStatus(ack);
    check(service.last.getRemoteConfigStatus().equals(ack), "ACK sent immediately");
    service.callback.onRequestFailed(new java.io.IOException("lost ACK"));
    service.capture();
    check(service.last.getRemoteConfigStatus().equals(ack), "failed request recipe restored");
    service.capture();
    check(!service.last.hasRemoteConfigStatus(), "unchanged ACK compressed");
    service.callback.onRequestSuccess(
        Response.create(
            ServerToAgent.newBuilder()
                .setInstanceUid(first.getInstanceUid())
                .setFlags(ServerToAgentFlags.ServerToAgentFlags_ReportFullState.getNumber())
                .build()));
    service.capture();
    check(
        service.last.hasAgentDescription() && service.last.getRemoteConfigStatus().equals(ack),
        "ReportFullState restores description and ACK");
    ByteString replacement = ByteString.copyFrom(new byte[16]);
    service.callback.onRequestSuccess(
        Response.create(
            ServerToAgent.newBuilder()
                .setInstanceUid(first.getInstanceUid())
                .setAgentIdentification(
                    AgentIdentification.newBuilder().setNewInstanceUid(replacement))
                .build()));
    service.capture();
    check(service.last.getInstanceUid().equals(replacement), "server reassigned UID");
    client.close();
    check(service.last.hasAgentDisconnect(), "disconnect on close");
    client.close();
    check(service.stops == 1, "idempotent close");

    RetryPeriodicDelay delay = RetryPeriodicDelay.create(Duration.ofSeconds(30));
    check(
        delay.getNextDelay().getSeconds() == 30 && delay.getNextDelay().getSeconds() == 60,
        "upstream exponential retry");
    delay.suggestDelay(Duration.ofSeconds(2));
    check(delay.getNextDelay().getSeconds() == 2, "Retry-After suggestion");
    delay.reset();
    check(delay.getNextDelay().getSeconds() == 30, "retry reset");
    for (int i = 0; i < 100; i++)
      check(!delay.getNextDelay().isNegative(), "backoff cannot overflow negative");
    check(
        RetryAfterParser.getInstance().tryParse("3").get().getSeconds() == 3,
        "Retry-After seconds");
    check(!RetryAfterParser.getInstance().tryParse("invalid").isPresent(), "invalid Retry-After");
    System.out.println(
        "PASS: upstream OpAMP capabilities, sequence, compression, full state, failed ACK retry,"
            + " UID assignment, disconnect, retry backoff");
  }

  private static final class FakeService implements RequestService {
    Callback callback;
    Supplier<Request> supplier;
    AgentToServer last;
    int stops;

    public void start(Callback callback, Supplier<Request> supplier) {
      this.callback = callback;
      this.supplier = supplier;
    }

    public void sendRequest() {
      capture();
    }

    void capture() {
      last = supplier.get().getAgentToServer();
    }

    public void stop() {
      stops++;
      capture();
    }
  }

  private static final class Callbacks implements OpampClient.Callbacks {
    public void onConnect(OpampClient client) {}

    public void onConnectFailed(OpampClient client, Throwable failure) {}

    public void onErrorResponse(OpampClient client, ServerErrorResponse error) {}

    public void onMessage(OpampClient client, MessageData data) {}
  }
}
