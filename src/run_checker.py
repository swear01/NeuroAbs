import subprocess
import time
import signal
import sys
import threading
import argparse
import re
import csv
from datetime import datetime
import os
import shlex
MAX_RUNTIME = 23600
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
start_time = time.time()
process = None
max_depth = -1  # 记录最大深度值
data_records = []  # 存储时间戳和深度值的记录
lock = threading.Lock()  # 用于线程同步
stop_event = threading.Event()

def handle_exit(signum, frame):
    """处理退出信号"""
    global process
    elapsed_time = time.time() - start_time
    print(f"\nCommand stopped after {elapsed_time:.2f} seconds.")
    stop_event.set()
    save_records()  # 退出前保存数据
    if process and process.poll() is None:
        process.terminate()
    sys.exit(1)

def timeout_handler():
    """超时处理"""
    global process
    elapsed_time = time.time() - start_time
    print(f"\nCommand timed out after {elapsed_time:.2f} seconds.")
    stop_event.set()
    save_records()  # 超时前保存数据
    if process and process.poll() is None:
        process.terminate()
    sys.exit(1)

def save_records():
    """将深度记录保存到CSV"""
    if not data_records:
        print("\nNo BMC depth data recorded.")
        return

    filename = f"bmc_depth_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    first_timestamp = data_records[0]["Timestamp"]
    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Timestamp", "Max Depth", "Elapsed Seconds"])
        writer.writeheader()
        for record in data_records:
            writer.writerow({
                "Timestamp": record["Timestamp"].isoformat(),
                "Max Depth": record["Max Depth"],
                "Elapsed Seconds": (record["Timestamp"] - first_timestamp).total_seconds(),
            })
    print(f"\nData saved to {filename}")

def read_output(stream):
    """持续读取命令输出"""
    global max_depth
    pattern = re.compile(r"bmc depth:\s*(\d+)")
    
    while True:
        line = stream.readline()
        if not line:
            break
        print(line.strip())  # 实时打印输出
        match = pattern.search(line)
        if match:
            current_depth = int(match.group(1))
            with lock:
                if current_depth > max_depth:
                    max_depth = current_depth

def record_data():
    """每隔3秒记录数据"""
    while not stop_event.wait(3):
        with lock:
            if max_depth == -1:  # 还没有数据时跳过
                continue
            elapsed = time.time() - start_time
            if elapsed > MAX_RUNTIME:
                break
            data_records.append({
                "Timestamp": datetime.now(),
                "Max Depth": max_depth
            })

def run_command_with_timeout(command, timeout):
    global process
    timer = threading.Timer(timeout, timeout_handler)
    record_thread = None
    timer.start()

    try:
        if not os.environ.get("RIC3_TMP_DIR"):
            ric3_tmp_dir = os.path.join(PROJECT_ROOT, ".tmp", "rIC3")
            os.makedirs(ric3_tmp_dir, exist_ok=True)
            os.environ["RIC3_TMP_DIR"] = ric3_tmp_dir
            print(f"Using RIC3_TMP_DIR={ric3_tmp_dir}")

        # 使用Popen来实时获取输出
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # 启动输出读取线程
        output_thread = threading.Thread(target=read_output, args=(process.stdout,))
        output_thread.daemon = True  # 设置为守护线程
        output_thread.start()

        # 启动数据记录线程
        record_thread = threading.Thread(target=record_data)
        record_thread.start()

        # 等待进程结束
        process.wait()
        elapsed_time = time.time() - start_time

        if process.returncode == 0:
            print(f"Command completed in {elapsed_time:.2f} seconds.")
        else:
            print(f"Command completed in {elapsed_time:.2f} seconds.")
            print(f"Command failed with return code {process.returncode}.")
            sys.exit(process.returncode)
        
    except Exception as e:
        print(f"Error while running command: {e}")
    finally:
        stop_event.set()
        timer.cancel()
        if record_thread and record_thread.is_alive():
            record_thread.join(timeout=1)
        save_records()  # 最终保存数据
        if process and process.poll() is None:
            process.terminate()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    parser = argparse.ArgumentParser(description="Run a command with a time limit.")
    parser.add_argument(
        "command",
        type=str,
        help="The command to run (enclose the command in quotes if it contains spaces)."
    )
    args = parser.parse_args()
    command_tokens = shlex.split(args.command)
    if command_tokens and command_tokens[0].startswith("-"):
        print(
            "Error: command starts with an option, not an executable. "
            "Did $RIC3_BIN expand to an empty string? Set it first, e.g. "
            "export RIC3_BIN=/data/zhiyuany/rIC3-HWMCC24/rIC3"
        )
        sys.exit(2)

    model_path = None
    for token in command_tokens:
        if token.endswith((".btor2", ".aig", ".btor")):
            model_path = token
            break

    if model_path and os.path.isabs(model_path):
        extracted_path = os.path.dirname(model_path)
        print(f"Extracted path: {extracted_path}")
        try:
            os.chdir(extracted_path)
            print(f"Changed working directory to: {os.getcwd()}")
        except FileNotFoundError:
            print(f"Error: The path '{extracted_path}' does not exist.")
    elif model_path:
        print(f"Using relative model path without changing directory: {model_path}")
    else:
        print("No model path found in the command.")
    if model_path and not os.path.exists(model_path):
        print(f"Error: model file does not exist: {model_path}")
        sys.exit(2)
    run_command_with_timeout(args.command, MAX_RUNTIME)
