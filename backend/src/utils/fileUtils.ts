/**
 * File utility functions
 * Handles file operations and path management
 */

import * as fs from "fs";
import * as path from "path";
import { v4 as uuidv4 } from "uuid";

/**
 * Ensure directory exists, create if it doesn't
 */
export function ensureDirectoryExists(dirPath: string): void {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

/**
 * Generate a unique filename
 */
export function generateUniqueFilename(originalFilename: string): string {
  const ext = path.extname(originalFilename);
  const baseName = path.basename(originalFilename, ext);
  const uniqueId = uuidv4();
  return `${baseName}_${uniqueId}${ext}`;
}

/**
 * Get file extension from filename
 */
export function getFileExtension(filename: string): string {
  return path.extname(filename).toLowerCase();
}

/**
 * Check if file is a valid video format
 */
export function isValidVideoFormat(filename: string): boolean {
  const validExtensions = [".mp4", ".mov", ".avi", ".mkv"];
  const ext = getFileExtension(filename);
  return validExtensions.includes(ext);
}

/**
 * Check if file is a valid image format
 */
export function isValidImageFormat(filename: string): boolean {
  const validExtensions = [".jpg", ".jpeg", ".png", ".heic", ".webp"];
  const ext = getFileExtension(filename);
  return validExtensions.includes(ext);
}

/**
 * Get upload directory path
 */
export function getUploadPath(subfolder: string = ""): string {
  const basePath = path.join(process.cwd(), "uploads");
  if (subfolder) {
    return path.join(basePath, subfolder);
  }
  return basePath;
}
