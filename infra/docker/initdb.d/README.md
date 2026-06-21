# initdb.d
#
# SQL files placed here are run by the postgres image on first
# startup (when the data volume is empty). The pgvector extension
# is enabled by the application code on first connection; do NOT
# enable it here.
#
# Examples of files you might add:
#   00-extensions.sql    -- CREATE EXTENSION ...
#   01-grants.sql        -- GRANT ... ON DATABASE ... TO ...
#
# All files must be idempotent (use ``IF NOT EXISTS``) because they
# re-run if the volume is recreated.