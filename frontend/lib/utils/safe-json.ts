/**
 * Safe JSON parsing utilities
 * Prevents crashes from malformed JSON in database or API responses
 */

/**
 * Safely parse JSON with a fallback value
 * @param value - The string value to parse (can be null/undefined)
 * @param fallback - The fallback value if parsing fails
 * @returns The parsed value or the fallback
 */
export function safeParseJson<T>(
  value: string | null | undefined,
  fallback: T
): T {
  if (!value) return fallback;

  // If already an object (not a string), return as-is
  if (typeof value === 'object') return value as T;

  try {
    return JSON.parse(value) as T;
  } catch {
    if (process.env.NODE_ENV === 'development') {
      console.warn('Failed to parse JSON, using fallback:', { value: value.substring(0, 100) });
    }
    return fallback;
  }
}

/**
 * Safely parse JSON or return the original value if already parsed
 * Useful when data might come as string or already parsed object
 */
export function safeParseJsonOrValue<T>(
  value: string | T | null | undefined,
  fallback: T
): T {
  if (value === null || value === undefined) return fallback;
  if (typeof value !== 'string') return value;
  return safeParseJson(value, fallback);
}

/**
 * Default fallback values for common types
 */
export const DEFAULT_VEHICLE_INFO = {
  type: 'unknown',
  brand: 'Unknown',
  model: 'Unknown',
  color: 'Unknown',
  confidence: 0,
};

export const DEFAULT_DAMAGE_INFO = {
  scratches: { count: 0, detected: false },
  dents: { count: 0, detected: false },
  rust: { count: 0, detected: false },
  severity: 'low' as const,
  locations: [],
};

export const DEFAULT_EXHAUST_INFO = {
  type: 'unknown',
  confidence: 0,
};

export const DEFAULT_ODOMETER_INFO = {
  value: null,
  confidence: 0,
  speedometer_image_path: null,
};
