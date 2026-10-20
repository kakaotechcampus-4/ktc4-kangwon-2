/** Already-started writes must settle before a new reader takes its server snapshot. */
export function createMutationBarrier<K>() {
  const pending = new Map<K, Promise<void>>();

  function track<T>(scope: K, work: Promise<T>): Promise<T> {
    // Keep only completion, never response payloads or a nested history of settled results.
    const current = Promise.allSettled([pending.get(scope), work]).then(() => undefined);
    pending.set(scope, current);
    void current.then(() => {
      // An older completion must not remove writes registered after it.
      if (pending.get(scope) === current) pending.delete(scope);
    });
    return work;
  }

  async function wait(scope: K): Promise<void> {
    // A write may be registered while the previous barrier is still being awaited.
    let current = pending.get(scope);
    while (current) {
      await current;
      current = pending.get(scope);
    }
  }

  return { track, wait };
}
