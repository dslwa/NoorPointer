-- psql script: create the isolated test database without changing application data.
SELECT 'CREATE DATABASE noorpointer_test OWNER noor'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'noorpointer_test')
\gexec
