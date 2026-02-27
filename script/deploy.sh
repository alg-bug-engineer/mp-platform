#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$ROOT_DIR/run"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$PID_DIR/content-studio.pid"
LOG_FILE="$LOG_DIR/content-studio.log"

PYTHON_BIN="${PYTHON_BIN:-/Users/zhangqilai/miniconda3/envs/lc/bin/python}"
PIP_BIN="${PIP_BIN:-/Users/zhangqilai/miniconda3/envs/lc/bin/pip}"
NPM_BIN="${NPM_BIN:-npm}"

DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-$ROOT_DIR/.env.deploy}"
DEPLOY_ENV_FILE_EXPLICIT=0
JIMENG_AK_ARG=""
JIMENG_SK_ARG=""
JIMENG_REQ_KEY_ARG=""
JIMENG_FALLBACK_REQ_KEYS_ARG=""
JIMENG_SCALE_ARG=""
JIMENG_MAX_RETRIES_ARG=""

print_usage() {
  cat <<'USAGE'
Usage: script/deploy.sh <command> [options]

Commands:
  start            Build + deploy + start service in background
  stop             Stop service
  restart          Restart service
  status           Show service status
  container-start  Run container entrypoint flow in foreground (install + init + run)
  help             Show this help

Options:
  --env-file <path>                    Load environment variables from file (default: .env.deploy)
  --jimeng-ak <value>                  Override JIMENG_AK for this execution
  --jimeng-sk <value>                  Override JIMENG_SK for this execution
  --jimeng-req-key <value>             Override JIMENG_REQ_KEY
  --jimeng-fallback-req-keys <value>   Override JIMENG_FALLBACK_REQ_KEYS
  --jimeng-scale <value>               Override JIMENG_SCALE
  --jimeng-max-retries <value>         Override JIMENG_MAX_RETRIES

Examples:
  script/deploy.sh restart --jimeng-ak xxx --jimeng-sk yyy
  script/deploy.sh start --env-file .env.deploy
  script/deploy.sh container-start
USAGE
}

mask_secret() {
  local value="${1:-}"
  local len="${#value}"
  if [[ "$len" -eq 0 ]]; then
    echo "(empty)"
  elif [[ "$len" -le 6 ]]; then
    echo "******"
  else
    echo "${value:0:3}***${value: -3}"
  fi
}

is_valid_ipv4() {
  local ip="${1:-}"
  [[ "$ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1
  local part
  IFS='.' read -r -a parts <<< "$ip"
  for part in "${parts[@]}"; do
    if (( part < 0 || part > 255 )); then
      return 1
    fi
  done
  return 0
}

fetch_public_ipv4() {
  local ip=""
  local providers=(
    "https://api.ipify.org"
    "https://ifconfig.me/ip"
    "https://ipv4.icanhazip.com"
  )

  if command -v curl >/dev/null 2>&1; then
    local url=""
    for url in "${providers[@]}"; do
      ip="$(curl -fsS --max-time 5 "$url" 2>/dev/null | tr -d '[:space:]' || true)"
      if is_valid_ipv4 "$ip"; then
        echo "$ip"
        return 0
      fi
    done
  fi

  if command -v wget >/dev/null 2>&1; then
    local url=""
    for url in "${providers[@]}"; do
      ip="$(wget -qO- --timeout=5 "$url" 2>/dev/null | tr -d '[:space:]' || true)"
      if is_valid_ipv4 "$ip"; then
        echo "$ip"
        return 0
      fi
    done
  fi

  return 1
}

merge_whitelist_ips() {
  local new_ip="${1:-}"
  local current="${WECHAT_WHITELIST_IPS:-}"
  local merged=""
  merged="$(printf '%s\n%s\n' "$current" "$new_ip" | tr ',; \t' '\n' | sed '/^$/d' | awk '!seen[$0]++' | paste -sd, -)"
  export WECHAT_WHITELIST_IPS="$merged"
}

ensure_wechat_whitelist_ips() {
  if [[ -n "${WECHAT_WHITELIST_IPS:-}" ]]; then
    return 0
  fi

  local detected_ip=""
  if detected_ip="$(fetch_public_ipv4)"; then
    merge_whitelist_ips "$detected_ip"
    echo "[deploy] Auto-detected WECHAT_WHITELIST_IPS=$WECHAT_WHITELIST_IPS"
  else
    echo "[deploy] Warning: failed to auto-detect public IPv4, WECHAT_WHITELIST_IPS remains empty"
  fi
}

load_env_file() {
  local env_file="$1"
  if [[ ! -f "$env_file" ]]; then
    echo "[deploy] Env file not found: $env_file"
    exit 1
  fi
  echo "[deploy] Loading env file: $env_file"
  set -a
  # shellcheck source=/dev/null
  source "$env_file"
  set +a
}

apply_runtime_overrides() {
  if [[ -n "$JIMENG_AK_ARG" ]]; then
    export JIMENG_AK="$JIMENG_AK_ARG"
  fi
  if [[ -n "$JIMENG_SK_ARG" ]]; then
    export JIMENG_SK="$JIMENG_SK_ARG"
  fi
  if [[ -n "$JIMENG_REQ_KEY_ARG" ]]; then
    export JIMENG_REQ_KEY="$JIMENG_REQ_KEY_ARG"
  fi
  if [[ -n "$JIMENG_FALLBACK_REQ_KEYS_ARG" ]]; then
    export JIMENG_FALLBACK_REQ_KEYS="$JIMENG_FALLBACK_REQ_KEYS_ARG"
  fi
  if [[ -n "$JIMENG_SCALE_ARG" ]]; then
    export JIMENG_SCALE="$JIMENG_SCALE_ARG"
  fi
  if [[ -n "$JIMENG_MAX_RETRIES_ARG" ]]; then
    export JIMENG_MAX_RETRIES="$JIMENG_MAX_RETRIES_ARG"
  fi
}

prepare_runtime_env() {
  if [[ -n "$DEPLOY_ENV_FILE" && -f "$DEPLOY_ENV_FILE" ]]; then
    load_env_file "$DEPLOY_ENV_FILE"
  elif [[ -n "$DEPLOY_ENV_FILE" ]]; then
    if [[ "$DEPLOY_ENV_FILE_EXPLICIT" -eq 1 ]]; then
      echo "[deploy] Env file not found: $DEPLOY_ENV_FILE"
      exit 1
    fi
    echo "[deploy] Env file not found, skip: $DEPLOY_ENV_FILE"
  fi
  apply_runtime_overrides
  ensure_wechat_whitelist_ips
}

print_runtime_summary() {
  echo "[deploy] Jimeng env -> AK: $(mask_secret "${JIMENG_AK:-}") | SK: $(mask_secret "${JIMENG_SK:-}") | REQ_KEY: ${JIMENG_REQ_KEY:-jimeng_t2i_v40}"
  echo "[deploy] WeChat whitelist IPs -> ${WECHAT_WHITELIST_IPS:-"(empty)"}"
}

parse_options() {
  local opt_value=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --env-file)
        opt_value="${2:-}"
        if [[ -z "$opt_value" || "$opt_value" == --* ]]; then
          echo "[deploy] Option --env-file requires a value"
          exit 1
        fi
        DEPLOY_ENV_FILE="$opt_value"
        DEPLOY_ENV_FILE_EXPLICIT=1
        shift 2
        ;;
      --env-file=*)
        DEPLOY_ENV_FILE="${1#*=}"
        DEPLOY_ENV_FILE_EXPLICIT=1
        shift
        ;;
      --jimeng-ak)
        opt_value="${2:-}"
        if [[ -z "$opt_value" || "$opt_value" == --* ]]; then
          echo "[deploy] Option --jimeng-ak requires a value"
          exit 1
        fi
        JIMENG_AK_ARG="$opt_value"
        shift 2
        ;;
      --jimeng-ak=*)
        JIMENG_AK_ARG="${1#*=}"
        shift
        ;;
      --jimeng-sk)
        opt_value="${2:-}"
        if [[ -z "$opt_value" || "$opt_value" == --* ]]; then
          echo "[deploy] Option --jimeng-sk requires a value"
          exit 1
        fi
        JIMENG_SK_ARG="$opt_value"
        shift 2
        ;;
      --jimeng-sk=*)
        JIMENG_SK_ARG="${1#*=}"
        shift
        ;;
      --jimeng-req-key)
        opt_value="${2:-}"
        if [[ -z "$opt_value" || "$opt_value" == --* ]]; then
          echo "[deploy] Option --jimeng-req-key requires a value"
          exit 1
        fi
        JIMENG_REQ_KEY_ARG="$opt_value"
        shift 2
        ;;
      --jimeng-req-key=*)
        JIMENG_REQ_KEY_ARG="${1#*=}"
        shift
        ;;
      --jimeng-fallback-req-keys)
        opt_value="${2:-}"
        if [[ -z "$opt_value" || "$opt_value" == --* ]]; then
          echo "[deploy] Option --jimeng-fallback-req-keys requires a value"
          exit 1
        fi
        JIMENG_FALLBACK_REQ_KEYS_ARG="$opt_value"
        shift 2
        ;;
      --jimeng-fallback-req-keys=*)
        JIMENG_FALLBACK_REQ_KEYS_ARG="${1#*=}"
        shift
        ;;
      --jimeng-scale)
        opt_value="${2:-}"
        if [[ -z "$opt_value" || "$opt_value" == --* ]]; then
          echo "[deploy] Option --jimeng-scale requires a value"
          exit 1
        fi
        JIMENG_SCALE_ARG="$opt_value"
        shift 2
        ;;
      --jimeng-scale=*)
        JIMENG_SCALE_ARG="${1#*=}"
        shift
        ;;
      --jimeng-max-retries)
        opt_value="${2:-}"
        if [[ -z "$opt_value" || "$opt_value" == --* ]]; then
          echo "[deploy] Option --jimeng-max-retries requires a value"
          exit 1
        fi
        JIMENG_MAX_RETRIES_ARG="$opt_value"
        shift 2
        ;;
      --jimeng-max-retries=*)
        JIMENG_MAX_RETRIES_ARG="${1#*=}"
        shift
        ;;
      -h|--help)
        print_usage
        exit 0
        ;;
      *)
        echo "[deploy] Unknown option: $1"
        print_usage
        exit 1
        ;;
    esac
  done
}

ensure_dirs() {
  mkdir -p "$PID_DIR" "$LOG_DIR"
}

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
  fi
  return 1
}

install_backend_deps() {
  echo "[deploy] Installing backend dependencies..."
  cd "$ROOT_DIR"
  "$PIP_BIN" install -r requirements.txt
}

install_frontend_deps() {
  echo "[deploy] Installing frontend dependencies..."
  cd "$ROOT_DIR/web_ui"
  "$NPM_BIN" install
}

ensure_config() {
  cd "$ROOT_DIR"
  if [[ ! -f "config.yaml" ]]; then
    echo "[deploy] config.yaml not found, creating from config.example.yaml"
    cp config.example.yaml config.yaml
  fi
}

init_system() {
  echo "[deploy] Initializing system..."
  cd "$ROOT_DIR"
  "$PYTHON_BIN" init_sys.py
}

build_frontend() {
  echo "[deploy] Building frontend..."
  cd "$ROOT_DIR/web_ui"
  "$NPM_BIN" run build

  echo "[deploy] Syncing frontend dist to static/..."
  cd "$ROOT_DIR"
  rsync -a --delete web_ui/dist/ static/
}

start_service() {
  ensure_dirs

  if is_running; then
    echo "[deploy] Service already running (pid=$(cat "$PID_FILE"))."
    return 0
  fi

  install_backend_deps
  install_frontend_deps
  ensure_config
  init_system
  build_frontend
  print_runtime_summary

  echo "[deploy] Starting service..."
  cd "$ROOT_DIR"
  nohup "$PYTHON_BIN" main.py -job True -init False >"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"

  sleep 1
  if is_running; then
    echo "[deploy] Service started (pid=$(cat "$PID_FILE"))."
    echo "[deploy] Log file: $LOG_FILE"
  else
    echo "[deploy] Failed to start service. Check log: $LOG_FILE"
    exit 1
  fi
}

stop_service() {
  if ! [[ -f "$PID_FILE" ]]; then
    echo "[deploy] No pid file found. Service may not be running."
    return 0
  fi

  local pid
  pid="$(cat "$PID_FILE")"

  if [[ -z "$pid" ]]; then
    echo "[deploy] Empty pid file, removing stale file."
    rm -f "$PID_FILE"
    return 0
  fi

  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "[deploy] Stopping service (pid=$pid)..."
    kill "$pid" >/dev/null 2>&1 || true

    for _ in {1..20}; do
      if kill -0 "$pid" >/dev/null 2>&1; then
        sleep 0.5
      else
        break
      fi
    done

    if kill -0 "$pid" >/dev/null 2>&1; then
      echo "[deploy] Force killing service (pid=$pid)..."
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi

    echo "[deploy] Service stopped."
  else
    echo "[deploy] Process not running, removing stale pid file."
  fi

  rm -f "$PID_FILE"
}

status_service() {
  if is_running; then
    echo "[deploy] Service is running (pid=$(cat "$PID_FILE"))."
    echo "[deploy] Log file: $LOG_FILE"
  else
    echo "[deploy] Service is not running."
  fi
}

run_container_entrypoint() {
  cd "$ROOT_DIR"
  if [[ -f "install.sh" ]]; then
    # shellcheck source=/dev/null
    source install.sh
  fi
  print_runtime_summary
  exec "$PYTHON_BIN" main.py -job True -init True
}

main() {
  local cmd="${1:-help}"
  if [[ $# -gt 0 ]]; then
    shift
  fi
  parse_options "$@"

  case "$cmd" in
    start)
      prepare_runtime_env
      start_service
      ;;
    stop)
      stop_service
      ;;
    restart)
      stop_service
      prepare_runtime_env
      start_service
      ;;
    status)
      status_service
      ;;
    container-start)
      prepare_runtime_env
      run_container_entrypoint
      ;;
    help|-h|--help)
      print_usage
      ;;
    *)
      echo "[deploy] Unknown command: $cmd"
      print_usage
      exit 1
      ;;
  esac
}

main "$@"
