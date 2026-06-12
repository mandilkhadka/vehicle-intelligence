/**
 * Shared API error helpers.
 *
 * Lives in its own module (not lib/api.ts) so component tests that
 * `jest.mock("@/lib/api")` still get the real implementations.
 */

import axios from "axios";

/**
 * Extract a human-readable message from any thrown error, preferring the
 * backend's own `message`/`error` payload over axios's generic
 * "Request failed with status code N".
 */
export function getApiErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as
      | { message?: string; error?: string }
      | undefined;
    return data?.message || data?.error || err.message || fallback;
  }
  return err instanceof Error && err.message ? err.message : fallback;
}

/**
 * True when the error is an HTTP 404/410 — i.e. the resource is gone and
 * retrying will never succeed.
 */
export function isNotFoundError(err: unknown): boolean {
  if (!axios.isAxiosError(err)) return false;
  const status = err.response?.status;
  return status === 404 || status === 410;
}
