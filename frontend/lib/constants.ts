/**
 * Frontend constants re-exported from shared
 * This allows the frontend to import from @/lib/constants
 */

// Re-export from shared (using relative path since Next.js handles this)
export { PROGRESS, FILE_LIMITS, API_CODES } from '../../shared/constants';

// Type re-exports
export type { ProgressStage, ApiErrorCode } from '../../shared/constants';
