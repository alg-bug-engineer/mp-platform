#!/bin/bash
set -euo pipefail

cd /app/
exec bash script/deploy.sh container-start "$@"
