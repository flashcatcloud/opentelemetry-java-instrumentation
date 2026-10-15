/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation.opampclient.internal.request.service;

import io.opentelemetry.javaagent.degradation.opampclient.internal.connectivity.http.HttpErrorException;
import io.opentelemetry.javaagent.degradation.opampclient.internal.connectivity.http.HttpSender;
import io.opentelemetry.javaagent.degradation.opampclient.internal.connectivity.http.RetryAfterParser;
import io.opentelemetry.javaagent.degradation.opampclient.internal.request.Request;
import io.opentelemetry.javaagent.degradation.opampclient.internal.request.delay.AcceptsDelaySuggestion;
import io.opentelemetry.javaagent.degradation.opampclient.internal.request.delay.PeriodicDelay;
import io.opentelemetry.javaagent.degradation.opampclient.internal.request.delay.RetryPeriodicDelay;
import io.opentelemetry.javaagent.degradation.opampclient.internal.response.OpampServerResponseException;
import io.opentelemetry.javaagent.degradation.opampclient.internal.response.Response;
import io.opentelemetry.javaagent.degradation.opampclient.request.service.RequestService;
import java.io.IOException;
import java.time.Duration;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;
import javax.annotation.Nullable;
import opamp.proto.v1.Opamp.AgentToServer;
import opamp.proto.v1.Opamp.ServerErrorResponse;
import opamp.proto.v1.Opamp.ServerErrorResponseType;
import opamp.proto.v1.Opamp.ServerToAgent;

public final class HttpRequestService implements RequestService {
  private final HttpSender requestSender;
  // must be a single threaded executor, the code in this class relies on requests being processed
  // serially
  private final ScheduledExecutorService executorService;
  private final AtomicBoolean isRunning = new AtomicBoolean(false);
  private final AtomicBoolean hasStopped = new AtomicBoolean(false);
  private final ConnectionStatus connectionStatus;
  private final AtomicReference<ScheduledFuture<?>> scheduledTask = new AtomicReference<>();
  private final RetryAfterParser retryAfterParser;
  @Nullable private Callback callback;
  @Nullable private Supplier<Request> requestSupplier;
  public static final PeriodicDelay DEFAULT_DELAY_BETWEEN_REQUESTS =
      PeriodicDelay.ofFixedDuration(Duration.ofSeconds(30));
  public static final PeriodicDelay DEFAULT_DELAY_BETWEEN_RETRIES =
      RetryPeriodicDelay.create(Duration.ofSeconds(30));

  /**
   * Creates an {@link HttpRequestService}.
   *
   * @param requestSender The HTTP sender implementation.
   */
  public static HttpRequestService create(HttpSender requestSender) {
    return create(requestSender, DEFAULT_DELAY_BETWEEN_REQUESTS, DEFAULT_DELAY_BETWEEN_RETRIES);
  }

  /**
   * Creates an {@link HttpRequestService}.
   *
   * @param requestSender The HTTP sender implementation.
   * @param periodicRequestDelay The time to wait between requests in general.
   * @param periodicRetryDelay The time to wait between retries.
   */
  public static HttpRequestService create(
      HttpSender requestSender,
      PeriodicDelay periodicRequestDelay,
      PeriodicDelay periodicRetryDelay) {
    return new HttpRequestService(
        requestSender,
        Executors.newSingleThreadScheduledExecutor(new DaemonThreadFactory()),
        periodicRequestDelay,
        periodicRetryDelay,
        RetryAfterParser.getInstance());
  }

  HttpRequestService(
      HttpSender requestSender,
      ScheduledExecutorService executorService,
      PeriodicDelay periodicRequestDelay,
      PeriodicDelay periodicRetryDelay,
      RetryAfterParser retryAfterParser) {
    this.requestSender = requestSender;
    this.executorService = executorService;
    this.retryAfterParser = retryAfterParser;
    this.connectionStatus = new ConnectionStatus(periodicRequestDelay, periodicRetryDelay);
  }

  @Override
  public void start(Callback callback, Supplier<Request> requestSupplier) {
    if (hasStopped.get()) {
      throw new IllegalStateException("HttpRequestService cannot start after it has been stopped.");
    }
    if (isRunning.compareAndSet(false, true)) {
      this.callback = callback;
      this.requestSupplier = requestSupplier;
      scheduleNextExecution();
    } else {
      throw new IllegalStateException("HttpRequestService is already running");
    }
  }

  @Override
  public void stop() {
    if (isRunning.compareAndSet(true, false)) {
      hasStopped.set(true);
      ScheduledFuture<?> pending = scheduledTask.get();
      if (pending != null) pending.cancel(false);
      executorService.execute(this::doSendRequest); // Best-effort final AgentDisconnect.
      executorService.shutdown();
      try {
        if (!executorService.awaitTermination(5, TimeUnit.SECONDS)) executorService.shutdownNow();
      } catch (InterruptedException interrupted) {
        executorService.shutdownNow();
        Thread.currentThread().interrupt();
      }
    }
  }

  @Override
  public void sendRequest() {
    if (!isRunning.get()) {
      throw new IllegalStateException("HttpRequestService is not running");
    }

    executorService.execute(
        () -> {
          // cancel the already scheduled task, a new one is created after current request is
          // processed
          ScheduledFuture<?> scheduledFuture = scheduledTask.get();
          if (scheduledFuture != null) {
            scheduledFuture.cancel(false);
          }
          sendAndScheduleNext();
        });
  }

  private void sendAndScheduleNext() {
    try {
      doSendRequest();
    } catch (RuntimeException failure) {
      getCallback().onRequestFailed(failure);
      connectionStatus.retryAfter(null);
    } finally {
      scheduleNextExecution();
    }
  }

  private void scheduleNextExecution() {
    if (!isRunning.get()) return;
    scheduledTask.set(
        executorService.schedule(
            this::sendAndScheduleNext,
            connectionStatus.getNextDelay().toNanos(),
            TimeUnit.NANOSECONDS));
  }

  private void doSendRequest() {
    AgentToServer agentToServer = Objects.requireNonNull(requestSupplier).get().getAgentToServer();

    byte[] data = agentToServer.toByteArray();
    try (HttpSender.Response response =
        requestSender.send(outputStream -> outputStream.write(data), data.length)) {
      if (isSuccessful(response)) {
        ServerToAgent serverToAgent = ServerToAgent.parseFrom(response.bodyInputStream());
        if (!serverToAgent.getInstanceUid().equals(agentToServer.getInstanceUid())) {
          throw new IOException("Unexpected OpAMP instance UID");
        }
        getCallback().onConnectionSuccess();
        handleHttpSuccess(Response.create(serverToAgent));
      } else {
        handleHttpError(response);
      }
    } catch (IOException e) {
      getCallback().onRequestFailed(e); // Retain the request recipe after I/O failure too.
      getCallback().onConnectionFailed(e);
      connectionStatus.retryAfter(null);
    } catch (RuntimeException e) {
      getCallback().onRequestFailed(e);
      connectionStatus.retryAfter(null);
    }
  }

  private void handleHttpError(HttpSender.Response response) {
    int errorCode = response.statusCode();
    getCallback().onRequestFailed(new HttpErrorException(errorCode, response.statusMessage()));

    if (errorCode == 503 || errorCode == 429) {
      String retryAfterHeader = response.getHeader("Retry-After");
      Duration retryAfter = null;
      if (retryAfterHeader != null) {
        Optional<Duration> duration = retryAfterParser.tryParse(retryAfterHeader);
        if (duration.isPresent()) {
          retryAfter = duration.get();
        }
      }
      connectionStatus.retryAfter(retryAfter);
    }
  }

  private static boolean isSuccessful(HttpSender.Response response) {
    return response.statusCode() >= 200 && response.statusCode() < 300;
  }

  private void handleHttpSuccess(Response response) {
    connectionStatus.success();
    ServerToAgent serverToAgent = response.getServerToAgent();

    if (serverToAgent.hasErrorResponse()) {
      handleErrorResponse(serverToAgent.getErrorResponse());
    } else {
      getCallback().onRequestSuccess(response);
    }
  }

  private void handleErrorResponse(ServerErrorResponse errorResponse) {
    if (errorResponse
        .getType()
        .equals(ServerErrorResponseType.ServerErrorResponseType_Unavailable)) {
      Duration retryAfter = null;
      if (errorResponse.getDetailsCase() == ServerErrorResponse.DetailsCase.RETRY_INFO) {
        retryAfter = Duration.ofNanos(errorResponse.getRetryInfo().getRetryAfterNanoseconds());
      }
      connectionStatus.retryAfter(retryAfter);
    }
    getCallback()
        .onRequestFailed(
            new OpampServerResponseException(errorResponse, errorResponse.getErrorMessage()));
  }

  private Callback getCallback() {
    return Objects.requireNonNull(callback);
  }

  // this class is only used from a single threaded ScheduledExecutorService, hence no
  // synchronization is needed
  private static class ConnectionStatus {
    private final PeriodicDelay periodicRequestDelay;
    private final PeriodicDelay periodicRetryDelay;

    private boolean retrying;
    private PeriodicDelay currentDelay;

    ConnectionStatus(PeriodicDelay periodicRequestDelay, PeriodicDelay periodicRetryDelay) {
      this.periodicRequestDelay = periodicRequestDelay;
      this.periodicRetryDelay = periodicRetryDelay;
      currentDelay = periodicRequestDelay;
    }

    void success() {
      // after successful request transition from retry to regular delay
      if (retrying) {
        retrying = false;
        periodicRequestDelay.reset();
        currentDelay = periodicRequestDelay;
      }
    }

    void retryAfter(@Nullable Duration retryAfter) {
      // after failed request transition from regular to retry delay
      if (!retrying) {
        retrying = true;
        periodicRetryDelay.reset();
        currentDelay = periodicRetryDelay;
        if (retryAfter != null && periodicRetryDelay instanceof AcceptsDelaySuggestion) {
          ((AcceptsDelaySuggestion) periodicRetryDelay).suggestDelay(retryAfter);
        }
      }
    }

    Duration getNextDelay() {
      return currentDelay.getNextDelay();
    }
  }
}
