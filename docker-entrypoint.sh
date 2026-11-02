#!/bin/sh
set -eu
mkdir -p /data /app/data
chown app:app /data /app/data
exec gosu app "$@"
