/**
 * Backend API server entry point
 * Sets up Express server and routes
 */

import express from "express";
import cors from "cors";
import path from "path";
import { initDatabase } from "./db/init";
import uploadRouter from "./routes/upload";
import jobsRouter from "./routes/jobs";
import inspectionsRouter from "./routes/inspections";

// Initialize database
initDatabase();

// Create Express app
const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Serve static files (uploads directory)
app.use("/uploads", express.static(path.join(process.cwd(), "uploads")));

// Health check endpoint
app.get("/health", (req, res) => {
  res.json({ status: "ok", message: "Vehicle Intelligence Platform API" });
});

// API routes
app.use("/api/upload", uploadRouter);
app.use("/api/jobs", jobsRouter);
app.use("/api/inspections", inspectionsRouter);

// Start server
app.listen(PORT, () => {
  console.log(`Backend API server running on http://localhost:${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
});
