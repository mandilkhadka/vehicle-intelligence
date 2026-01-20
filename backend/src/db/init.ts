/**
 * Database initialization module
 * Sets up SQLite database and creates tables with proper error handling
 */

import Database from "better-sqlite3";
import * as fs from "fs";
import * as path from "path";
import { config } from "../config/env";
import logger from "../utils/logger";

// Get database file path
const dbPath = path.join(process.cwd(), config.database.path);

// Read schema SQL file
const schemaPath = path.join(__dirname, "schema.sql");

/**
 * Initialize the database
 * Creates database file and runs schema SQL
 */
export function initDatabase(): Database.Database {
  try {
    // Check if schema file exists
    if (!fs.existsSync(schemaPath)) {
      throw new Error(`Schema file not found at ${schemaPath}`);
    }

    // Read schema SQL file
    const schema = fs.readFileSync(schemaPath, "utf-8");

    // Create database connection with WAL mode for better concurrency
    const db = new Database(dbPath, {
      verbose: config.env === "development" ? logger.debug.bind(logger) : undefined,
    });

    // Enable foreign keys
    db.pragma("foreign_keys = ON");

    // Enable WAL mode for better concurrency
    db.pragma("journal_mode = WAL");

    // Set busy timeout
    db.pragma("busy_timeout = 5000");

    // Execute schema SQL
    const statements = schema
      .split(";")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    for (const statement of statements) {
      if (statement.trim()) {
        try {
          db.exec(statement);
        } catch (error) {
          logger.warn({ error, statement }, "Failed to execute schema statement");
        }
      }
    }

    // Migrations: Add new columns if they don't exist
    try {
      const tableInfo = db.prepare("PRAGMA table_info(inspections)").all() as Array<{ name: string }>;
      const columnNames = tableInfo.map((col) => col.name);

      if (!columnNames.includes("exhaust_image_path")) {
        logger.info("Adding exhaust_image_path column to inspections table");
        db.exec("ALTER TABLE inspections ADD COLUMN exhaust_image_path TEXT");
      }
    } catch (error) {
      logger.warn({ error }, "Migration error (non-critical)");
    }

    logger.info({ dbPath }, "Database initialized successfully");

    return db;
  } catch (error) {
    logger.fatal({ error, dbPath }, "Failed to initialize database");
    throw error;
  }
}

/**
 * Get database instance
 * Creates new connection if needed
 */
let dbInstance: Database.Database | null = null;

export function getDatabase(): Database.Database {
  if (!dbInstance) {
    dbInstance = initDatabase();
  }
  return dbInstance;
}
