/**
 * Zod-based request validation helpers.
 *
 * Single validation mechanism for all routes (body, params, query). Throws a
 * 400 CustomError listing every issue, so the errorHandler emits the standard
 * envelope with code VALIDATION_ERROR.
 */

import { z } from "zod";
import { CustomError } from "../middleware/errorHandler";

function parseWith<T extends z.ZodTypeAny>(
  schema: T,
  data: unknown,
  what: string,
): z.infer<T> {
  const result = schema.safeParse(data);
  if (!result.success) {
    const issues = result.error.issues
      .map((i) => (i.path.length ? `${i.path.join(".")}: ${i.message}` : i.message))
      .join("; ");
    throw new CustomError(`Invalid ${what} — ${issues}`, 400, "VALIDATION_ERROR");
  }
  return result.data;
}

export function parseBody<T extends z.ZodTypeAny>(schema: T, body: unknown): z.infer<T> {
  return parseWith(schema, body, "request body");
}

export function parseParams<T extends z.ZodTypeAny>(schema: T, params: unknown): z.infer<T> {
  return parseWith(schema, params, "request parameters");
}

export function parseQuery<T extends z.ZodTypeAny>(schema: T, query: unknown): z.infer<T> {
  return parseWith(schema, query, "query parameters");
}
