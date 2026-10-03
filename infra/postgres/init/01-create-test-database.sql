-- Runs once, the first time the Postgres container starts with an empty volume.
-- The test suite uses its own database so it never touches development data.
CREATE DATABASE orderpulse_test OWNER orderpulse;
