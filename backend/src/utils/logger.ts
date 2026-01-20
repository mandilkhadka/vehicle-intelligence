/**
 * Structured logging utility
 * Uses Pino for high-performance JSON logging
 */

import pino from "pino";
import { config } from "../config/env";

const logger = pino({
  level: config.logging.level,
  ...(config.logging.pretty && {
    transport: {
      target: "pino-pretty",
      options: {
        colorize: true,
        translateTime: "HH:MM:ss Z",
        ignore: "pid,hostname",
      },
    },
  }),
  formatters: {
    level: (label) => {
      return { level: label.toUpperCase() };
    },
  },
  timestamp: pino.stdTimeFunctions.isoTime,
  base: {
    env: config.env,
  },
});

export default logger;
