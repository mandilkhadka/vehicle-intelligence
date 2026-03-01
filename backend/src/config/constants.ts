/**
 * Backend constants mirroring shared/constants.ts
 * Keep in sync with shared/constants.ts PROGRESS.SIMULATION values
 */

export const PROGRESS_SIMULATION = {
  INCREMENT: 5,
  INTERVAL_MS: 10000,
  MIN_PROGRESS: 20,
  MAX_PROGRESS: 85,
} as const;
