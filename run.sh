#!/usr/bin/env bash
# Start the chosen vector database, then run the solution in Docker on it.
#
#   ./run.sh --backend weaviate compare
#   ./run.sh --backend pgvector compare
#   ./run.sh --backend pgvector ask "What is the penalty in month 20?" --strategy markdown
#
# Without --backend, weaviate is used. Every argument is passed to run.py unchanged.
set -euo pipefail

cd "$(dirname "$0")"

backend="weaviate"
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend)   backend="$2"; args+=("$1" "$2"); shift 2 ;;
    --backend=*) backend="${1#--backend=}"; args+=("$1"); shift ;;
    *)           args+=("$1"); shift ;;
  esac
done

case "$backend" in
  weaviate) service="weaviate" ;;
  pgvector) service="postgres" ;;
  *) echo "Unknown backend '$backend'. Use weaviate or pgvector." >&2; exit 2 ;;
esac

if [[ ${#args[@]} -eq 0 ]]; then
  echo "Give a command, for example: ./run.sh --backend $backend compare" >&2
  exit 2
fi

docker compose --profile "$backend" up -d --wait "$service"
docker compose run --rm --build -e VECTOR_BACKEND="$backend" app python run.py "${args[@]}"
