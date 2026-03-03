#!/bin/sh
chown -R lapsora:lapsora /app/data
exec gosu lapsora "$@"
