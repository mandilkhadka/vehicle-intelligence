/**
 * Database initialization module
 * Sets up SQLite database and creates tables
 */

import Database from "better-sqlite3";
import * as fs from "fs";
import * as path from "path";

// Get database file path
const dbPath = path.join(process.cwd(), "vehicle_intelligence.db");

// Read schema SQL file
const schemaPath = path.join(__dirname, "schema.sql");
const schema = fs.readFileSync(schemaPath, "utf-8");

/**
 * Initialize the database
 * Creates database file and runs schema SQL
 */
export function initDatabase(): Database.Database {
  // Create database connection
  const db = new Database(dbPath);

  // Enable foreign keys
  db.pragma("foreign_keys = ON");

  // Execute schema SQL
  // Split by semicolon and execute each statement
  const statements = schema
    .split(";")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);

  for (const statement of statements) {
    if (statement.trim()) {
      db.exec(statement);
    }
  }

  // Migrations: Add new columns if they don't exist
  try {
    // Check if exhaust_image_path column exists
    const tableInfo = db.prepare("PRAGMA table_info(inspections)").all() as Array<{ name: string }>;
    const columnNames = tableInfo.map((col) => col.name);
    
    if (!columnNames.includes("exhaust_image_path")) {
      console.log("Adding exhaust_image_path column to inspections table...");
      db.exec("ALTER TABLE inspections ADD COLUMN exhaust_image_path TEXT");
    }
  } catch (error) {
    console.error("Migration error:", error);
    // Continue even if migration fails
  }

  console.log("Database initialized successfully");

  return db;
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
