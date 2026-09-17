import { ApiError } from "./api/client";

/** Retries a mutation with confirm=true if the server asks for
 * confirmation (409, matching the reference app's confirm() dialogs) and
 * the user agrees to a native confirm() prompt. */
export async function withConfirmRetry<T>(action: () => Promise<T>, retry: (confirm: boolean) => Promise<T>): Promise<T> {
  try {
    return await action();
  } catch (e) {
    if (e instanceof ApiError && e.needsConfirmation) {
      if (window.confirm(e.detail)) return retry(true);
      throw e;
    }
    throw e;
  }
}
