#!/bin/bash
set -e

# ---------------- 配置区 ----------------
LOCAL_PORT="7882"   # 可以手动指定，比如 2222；为空则自动找
REMOTE_PORT="51315"  # 可以手动指定，比如 10022；为空则自动找
FKQZ_URL="https://github.com/Sarfflow/rtunnel/releases/download/v1.0.0/rtunnel-linux"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="$SCRIPT_DIR/.bin"
FKQZ_BIN="$BIN_DIR/fkqz"
LOG_DIR="$SCRIPT_DIR/log"
# ----------------------------------------

# 找一个随机未占用端口
find_free_port() {
    while true; do
        # 使用 /dev/urandom 生成随机数，不依赖 $RANDOM
        PORT=$(( ( $(od -An -N2 -i /dev/urandom) % 50000 ) + 10000 ))

        if command -v lsof >/dev/null 2>&1; then
            if ! lsof -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
                echo $PORT
                return
            fi
        elif command -v ss >/dev/null 2>&1; then
            if ! ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[.:]$PORT\$"; then
                echo $PORT
                return
            fi
        elif command -v netstat >/dev/null 2>&1; then
            if ! netstat -tuln 2>/dev/null | awk '{print $4}' | grep -Eq "[.:]$PORT\$"; then
                echo $PORT
                return
            fi
        else
            echo "没有可用的端口检查工具 (需要 lsof/ss/netstat)" >&2
            exit 1
        fi
    done
}

# 清理旧进程
cleanup_old() {
    echo ">>> 清理旧进程..."
    mkdir -p "$LOG_DIR"
    for pidfile in fkqz.pid sshd.pid; do
        PID_PATH="$LOG_DIR/$pidfile"
        if [ -f "$PID_PATH" ]; then
            PID=$(cat "$PID_PATH")
            if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
                echo ">>> 杀掉进程 $PID ($pidfile)"
                kill -15 "$PID" || true
                while kill -0 "$PID" 2>/dev/null; do
                    sleep 0.5
                done
            fi
            rm -f "$PID_PATH"
        fi
    done
}

# 下载 fkqz
prepare_fkqz() {
    if [ ! -x "$FKQZ_BIN" ]; then
        echo ">>> 未找到 fkqz，正在下载..."
        mkdir -p "$BIN_DIR"
        curl -L "$FKQZ_URL" -o "$FKQZ_BIN"
        chmod +x "$FKQZ_BIN"
        echo ">>> fkqz 已下载到 $FKQZ_BIN"
    else
        echo ">>> 已存在 fkqz，跳过下载"
    fi
}

# 启动 fkqz
start_fkqz() {
    if [ -z "$LOCAL_PORT" ]; then
        LOCAL_PORT=$(find_free_port)
    fi
    if [ -z "$REMOTE_PORT" ]; then
        while true; do
            REMOTE_PORT=$(find_free_port)
            [ "$REMOTE_PORT" -ne "$LOCAL_PORT" ] && break
        done
    fi

    echo ">>> 启动 fkqz: local=$LOCAL_PORT, remote=$REMOTE_PORT"
    mkdir -p "$LOG_DIR"
    nohup "$FKQZ_BIN" "$LOCAL_PORT" "$REMOTE_PORT" -d >"$LOG_DIR/fkqz.log" 2>&1 &
    echo $! > "$LOG_DIR/fkqz.pid"
}

# 启动 sshd
start_sshd() {
    echo ">>> 启动 sshd, 端口 $LOCAL_PORT"
    mkdir -p /run/sshd
    mkdir -p "$LOG_DIR"
    nohup /usr/sbin/sshd -D -p "$LOCAL_PORT" >"$LOG_DIR/sshd.log" 2>&1 &
    echo $! > "$LOG_DIR/sshd.pid"
}

# ---------------- 主逻辑 ----------------
cleanup_old
prepare_fkqz
start_fkqz
start_sshd

echo ">>> 脚本执行完成"
echo ">>> fkqz 日志: $LOG_DIR/fkqz.log, PID: $(cat $LOG_DIR/fkqz.pid)"
echo ">>> sshd 日志: $LOG_DIR/sshd.log, PID: $(cat $LOG_DIR/sshd.pid)"
echo ">>> 映射到远程端口 $REMOTE_PORT"
