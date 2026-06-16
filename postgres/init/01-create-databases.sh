#!/usr/bin/env bash
set -euo pipefail

required_vars=(
  POSTGRES_APP_DB
  POSTGRES_APP_USER
  POSTGRES_APP_PASSWORD
  POSTGRES_AUDIT_DB
  POSTGRES_AUDIT_USER
  POSTGRES_AUDIT_PASSWORD
)

for var in "${required_vars[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "Missing required PostgreSQL init variable: ${var}" >&2
    exit 1
  fi
done

validate_identifier() {
  local var_name="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "${var_name} must be a simple SQL identifier: ${value}" >&2
    exit 1
  fi
}

escape_sql_literal() {
  local value="$1"
  printf "%s" "${value//\'/\'\'}"
}

validate_identifier POSTGRES_APP_DB "$POSTGRES_APP_DB"
validate_identifier POSTGRES_APP_USER "$POSTGRES_APP_USER"
validate_identifier POSTGRES_AUDIT_DB "$POSTGRES_AUDIT_DB"
validate_identifier POSTGRES_AUDIT_USER "$POSTGRES_AUDIT_USER"

create_role_if_missing() {
  local role_name="$1"
  local role_password="$2"
  local escaped_password
  escaped_password="$(escape_sql_literal "$role_password")"
  if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_roles WHERE rolname='${role_name}'" | grep -q 1; then
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
      CREATE ROLE "${role_name}" WITH LOGIN PASSWORD '${escaped_password}';
EOSQL
  fi
}

create_database_if_missing() {
  local database_name="$1"
  local owner_name="$2"
  if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_database WHERE datname='${database_name}'" | grep -q 1; then
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
      CREATE DATABASE "${database_name}" OWNER "${owner_name}" ENCODING 'UTF8';
EOSQL
  fi
}

create_role_if_missing "$POSTGRES_APP_USER" "$POSTGRES_APP_PASSWORD"
create_role_if_missing "$POSTGRES_AUDIT_USER" "$POSTGRES_AUDIT_PASSWORD"

create_database_if_missing "$POSTGRES_APP_DB" "$POSTGRES_APP_USER"
create_database_if_missing "$POSTGRES_AUDIT_DB" "$POSTGRES_AUDIT_USER"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_APP_DB" <<-EOSQL
  GRANT ALL PRIVILEGES ON DATABASE "${POSTGRES_APP_DB}" TO "${POSTGRES_APP_USER}";
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_AUDIT_DB" <<-EOSQL
  GRANT ALL PRIVILEGES ON DATABASE "${POSTGRES_AUDIT_DB}" TO "${POSTGRES_AUDIT_USER}";
EOSQL
