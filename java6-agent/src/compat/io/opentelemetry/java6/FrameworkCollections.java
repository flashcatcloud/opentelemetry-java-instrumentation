/* Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package io.opentelemetry.java6;
import java.util.Map;
import java8.util.function.BiConsumer;
import java8.util.function.Consumer;
import io.opentelemetry.sdk.metrics.internal.state.PooledHashMap;
/** Preserve the upstream pooled-map iteration contract when adapting Map defaults. */
public final class FrameworkCollections {
  private FrameworkCollections() {}
  public static <K,V> void forEach(Map<K,V> map,BiConsumer<? super K,? super V> action) {
    if(map instanceof PooledHashMap) ((PooledHashMap<K,V>)map).forEach(action);
    else java8.util.Maps.forEach(map,action);
  }
  public static <T> void forEach(Iterable<T> items,Consumer<? super T> action) {java8.lang.Iterables.forEach(items,action);}
}
