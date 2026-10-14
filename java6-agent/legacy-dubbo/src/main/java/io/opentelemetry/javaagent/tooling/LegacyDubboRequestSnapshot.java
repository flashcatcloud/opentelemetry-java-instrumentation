/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.javaagent.tooling;

import com.alibaba.dubbo.rpc.RpcInvocation;
import java.util.HashMap;

/** Retains propagation headers until a deferred Netty encoder consumes the request. */
public final class LegacyDubboRequestSnapshot {
  public static Object copyIfAsync(Object request) {
    if (!(request instanceof RpcInvocation) || !DubboTelemetry.INSTANCE.isAsyncRequest()) {
      return request;
    }
    RpcInvocation original = (RpcInvocation) request;
    RpcInvocation snapshot = new RpcInvocation(original);
    snapshot.setAttachments(new HashMap<String, String>(original.getAttachments()));
    return snapshot;
  }
  private LegacyDubboRequestSnapshot() {}
}
