-- PostgreSQL init script for AI Trading Desk
-- Creates database, enables UUID extensions.
-- Alembic manages table DDL.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
