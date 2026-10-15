/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.degradation.opampclient.internal.impl;

import com.google.protobuf.ByteString;
import io.opentelemetry.javaagent.degradation.opampclient.OpampClient;
import io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.AgentToServerAppenders;
import io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.RecipeManager;
import io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.RequestRecipe;
import io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders.AgentDescriptionAppender;
import io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders.AgentDisconnectAppender;
import io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders.CapabilitiesAppender;
import io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders.CustomCapabilitiesAppender;
import io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders.EffectiveConfigAppender;
import io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders.FlagsAppender;
import io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders.HealthAppender;
import io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders.InstanceUidAppender;
import io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders.RemoteConfigStatusAppender;
import io.opentelemetry.javaagent.degradation.opampclient.internal.impl.recipe.appenders.SequenceNumberAppender;
import io.opentelemetry.javaagent.degradation.opampclient.internal.request.Field;
import io.opentelemetry.javaagent.degradation.opampclient.internal.request.Request;
import io.opentelemetry.javaagent.degradation.opampclient.internal.response.MessageData;
import io.opentelemetry.javaagent.degradation.opampclient.internal.response.OpampServerResponseException;
import io.opentelemetry.javaagent.degradation.opampclient.internal.response.Response;
import io.opentelemetry.javaagent.degradation.opampclient.internal.state.ObservableState;
import io.opentelemetry.javaagent.degradation.opampclient.internal.state.State;
import io.opentelemetry.javaagent.degradation.opampclient.request.service.RequestService;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Supplier;
import javax.annotation.Nonnull;
import opamp.proto.v1.Opamp.AgentCapabilities;
import opamp.proto.v1.Opamp.AgentDescription;
import opamp.proto.v1.Opamp.AgentToServer;
import opamp.proto.v1.Opamp.ComponentHealth;
import opamp.proto.v1.Opamp.RemoteConfigStatus;
import opamp.proto.v1.Opamp.ServerErrorResponse;
import opamp.proto.v1.Opamp.ServerToAgent;
import opamp.proto.v1.Opamp.ServerToAgentFlags;

/**
 * This class is internal and is hence not for public use. Its APIs are unstable and can change at
 * any time.
 */
public final class OpampClientImpl
    implements OpampClient, ObservableState.Listener, RequestService.Callback, Supplier<Request> {
  private final RequestService requestService;
  private final AgentToServerAppenders appenders;
  private final OpampClientState state;
  private final RecipeManager recipeManager;
  private final AtomicBoolean hasStopped = new AtomicBoolean(false);
  private final Callbacks callbacks;

  /** Fields that must always be sent. */
  private static final List<Field> REQUIRED_FIELDS;

  /**
   * Fields that should only be sent in the first message and then omitted in following messages,
   * unless their value changes or the server requests a full message.
   *
   * <p>Refer to <a
   * href="https://github.com/open-telemetry/opamp-spec/blob/main/specification.md#agent-status-compression">the
   * docs</a> for more details.
   */
  private static final List<Field> COMPRESSABLE_FIELDS;

  static {
    // Required fields init
    List<Field> constantFields = new ArrayList<>();
    constantFields.add(Field.INSTANCE_UID);
    constantFields.add(Field.SEQUENCE_NUM);
    constantFields.add(Field.CAPABILITIES);
    REQUIRED_FIELDS = Collections.unmodifiableList(constantFields);

    // Compressable fields init
    List<Field> compressableFields = new ArrayList<>();
    compressableFields.add(Field.AGENT_DESCRIPTION);
    compressableFields.add(Field.CUSTOM_CAPABILITIES);
    compressableFields.add(Field.HEALTH);
    compressableFields.add(Field.EFFECTIVE_CONFIG);
    compressableFields.add(Field.REMOTE_CONFIG_STATUS);
    COMPRESSABLE_FIELDS = Collections.unmodifiableList(compressableFields);
  }

  public static OpampClientImpl create(
      RequestService requestService, OpampClientState state, Callbacks callbacks) {
    AgentToServerAppenders appenders =
        new AgentToServerAppenders(
            AgentDescriptionAppender.create(state.agentDescription),
            EffectiveConfigAppender.create(state.effectiveConfig),
            RemoteConfigStatusAppender.create(state.remoteConfigStatus),
            SequenceNumberAppender.create(state.sequenceNum),
            CapabilitiesAppender.create(state.capabilities),
            CustomCapabilitiesAppender.create(state.customCapabilities),
            HealthAppender.create(state.health),
            InstanceUidAppender.create(state.instanceUid),
            FlagsAppender.create(state.flags),
            AgentDisconnectAppender.create());
    OpampClientImpl client =
        new OpampClientImpl(
            requestService, appenders, state, RecipeManager.create(REQUIRED_FIELDS), callbacks);

    // Start
    requestService.start(client, client);
    client.disableCompression();
    client.startObservingStateChange();
    requestService.sendRequest();

    return client;
  }

  private OpampClientImpl(
      RequestService requestService,
      AgentToServerAppenders appenders,
      OpampClientState state,
      RecipeManager recipeManager,
      Callbacks callbacks) {
    this.requestService = requestService;
    this.appenders = appenders;
    this.state = state;
    this.recipeManager = recipeManager;
    this.callbacks = callbacks;
  }

  @Override
  public void close() {
    if (hasStopped.compareAndSet(false, true)) {
      stopObservingStateChange();
      prepareDisconnectRequest();
      requestService.stop();
    }
  }

  @Override
  public void setAgentDescription(@Nonnull AgentDescription agentDescription) {
    if (state.agentDescription.set(agentDescription)) {
      addFieldAndSend(Field.AGENT_DESCRIPTION);
    }
  }

  @Override
  public void setRemoteConfigStatus(@Nonnull RemoteConfigStatus remoteConfigStatus) {
    verifyCapability(AgentCapabilities.AgentCapabilities_ReportsRemoteConfig);
    if (state.remoteConfigStatus.set(remoteConfigStatus)) {
      addFieldAndSend(Field.REMOTE_CONFIG_STATUS);
    }
  }

  @Override
  public void setHealth(@Nonnull ComponentHealth health) {
    verifyCapability(AgentCapabilities.AgentCapabilities_ReportsHealth);
    if (state.health.set(health)) {
      addFieldAndSend(Field.HEALTH);
    }
  }

  @Override
  public void onConnectionSuccess() {
    callbacks.onConnect(this);
  }

  @Override
  public void onConnectionFailed(Throwable throwable) {
    callbacks.onConnectFailed(this, throwable);
  }

  @Override
  public void onRequestSuccess(Response response) {
    if (response == null) {
      return;
    }

    handleResponsePayload(response.getServerToAgent());
  }

  @Override
  public void onRequestFailed(Throwable throwable) {
    preserveFailedRequestRecipe();
    if (throwable instanceof OpampServerResponseException) {
      ServerErrorResponse errorResponse = ((OpampServerResponseException) throwable).errorResponse;
      callbacks.onErrorResponse(this, errorResponse);
    }
  }

  private void preserveFailedRequestRecipe() {
    RequestRecipe previous = recipeManager.previous();
    if (previous != null) {
      recipeManager.next().merge(previous);
    }
  }

  private void handleResponsePayload(ServerToAgent response) {
    int reportFullState = ServerToAgentFlags.ServerToAgentFlags_ReportFullState.getNumber();
    if ((response.getFlags() & reportFullState) == reportFullState) {
      disableCompression();
    }
    handleAgentIdentification(response);

    boolean notifyOnMessage = false;
    MessageData.Builder messageBuilder = MessageData.builder();

    if (response.hasRemoteConfig()) {
      notifyOnMessage = true;
      messageBuilder.setRemoteConfig(response.getRemoteConfig());
    }

    if (response.hasCustomMessage()) {
      notifyOnMessage = true;
      messageBuilder.setCustomMessage(response.getCustomMessage());
    }

    if (notifyOnMessage) {
      callbacks.onMessage(this, messageBuilder.build());
    }
  }

  private void handleAgentIdentification(ServerToAgent response) {
    if (response.hasAgentIdentification()) {
      ByteString newInstanceUid = response.getAgentIdentification().getNewInstanceUid();
      if (newInstanceUid.size() > 0) {
        state.instanceUid.set(newInstanceUid.toByteArray());
      }
    }
  }

  private void disableCompression() {
    recipeManager.next().addAllFields(COMPRESSABLE_FIELDS);
  }

  private void prepareDisconnectRequest() {
    recipeManager.next().addField(Field.AGENT_DISCONNECT);
  }

  @Override
  public Request get() {
    AgentToServer.Builder builder = AgentToServer.newBuilder();
    for (Field field : recipeManager.next().build().getFields()) {
      appenders.getForField(field).appendTo(builder);
    }
    Request request = Request.create(builder.build());
    state.sequenceNum.increment();
    return request;
  }

  private void startObservingStateChange() {
    for (State<?> state : state.getAll()) {
      if (state instanceof ObservableState) {
        ((ObservableState<?>) state).addListener(this);
      }
    }
  }

  private void stopObservingStateChange() {
    for (State<?> state : state.getAll()) {
      if (state instanceof ObservableState) {
        ((ObservableState<?>) state).removeListener(this);
      }
    }
  }

  @Override
  public void onStateUpdate(Field type) {
    addFieldAndSend(type);
  }

  private void addFieldAndSend(Field field) {
    recipeManager.next().addField(field);
    requestService.sendRequest();
  }

  private void verifyCapability(AgentCapabilities capabilityToCheck) {
    if ((state.capabilities.mustGet() & capabilityToCheck.getNumber()) == 0) {
      throw new IllegalStateException(
          "Required capability " + capabilityToCheck + " is not enabled");
    }
  }
}
