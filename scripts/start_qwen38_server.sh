#!/usr/bin/env bash
# --check validates and prints the pinned command without Docker, downloads or writes.
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 - "$script_dir/../data/qwen38_deployment.json" "$@" <<'PY'
import argparse
import csv
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

parser = argparse.ArgumentParser(description="Start the pinned Qwen3.8 image server on a Linux RTX 5090 host.")
parser.add_argument("default_deployment", type=Path, help=argparse.SUPPRESS)
parser.add_argument("--deployment", type=Path, help="Alternate recorded deployment manifest")
parser.add_argument("--check", action="store_true", help="Validate metadata and print the launch command; do not run it")
parser.add_argument("--inside-container", action="store_true", help="Run directly inside the pinned GPU image; do not invoke Docker")
parser.add_argument("--cache-dir", type=Path, default=Path("/workspace/qwen38-cache"), help="Persistent model cache on the GPU host")
parser.add_argument("--gpu", default="0", help="One host NVIDIA GPU index (default: 0)")
parser.add_argument("--name", default="pdf-qwen38", help="Docker container name")
args = parser.parse_args()

try:
    deployment = json.loads((args.deployment or args.default_deployment).read_text(encoding="utf-8"))
    runtime, server = deployment["runtime"], deployment["server"]
    if deployment["version"] != 1 or runtime["engine"] != "sglang":
        raise ValueError("Expected a version 1 SGLang deployment")
    if not re.fullmatch(r"[0-9a-f]{40}", deployment["revision"]):
        raise ValueError("Model revision must be an exact Hugging Face commit")
    if not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", runtime["image"]):
        raise ValueError("Runtime image must be pinned by SHA256 digest")
    if not re.fullmatch(r"[0-9a-f]{40}", runtime["commit"]):
        raise ValueError("Runtime build commit must be recorded")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", runtime["minimum_linux_driver"]):
        raise ValueError("Minimum Linux driver must be a recorded numeric version")
    if server["host"] != "127.0.0.1" or not 1 <= server["port"] <= 65535:
        raise ValueError("This launcher requires a loopback host and valid port")
    if server["enable_multimodal"] is not True or server["speculative_decoding"] is not False:
        raise ValueError("This pilot requires vision enabled and speculative decoding disabled")
    if deployment["max_running_requests"] != 1 or server["tensor_parallel_size"] != 1:
        raise ValueError("This pilot serves one request on one GPU")
    if "max_total_tokens" in server and (type(server["max_total_tokens"]) is not int
            or server["max_total_tokens"] < deployment["context_length"]):
        raise ValueError("The KV token pool must cover the recorded context length")
    if "constrained_json_disable_any_whitespace" in server and type(server["constrained_json_disable_any_whitespace"]) is not bool:
        raise ValueError("Compact JSON selection must be a boolean")
    if not re.fullmatch(r"[0-9]+", args.gpu):
        raise ValueError("--gpu must be one numeric GPU index")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", args.name):
        raise ValueError("Invalid Docker container name")
    cache_dir = args.cache_dir.expanduser().resolve()
    if "," in str(cache_dir):
        raise ValueError("--cache-dir cannot contain a comma (Docker mount syntax)")
except (KeyError, ValueError, TypeError, OSError) as exc:
    parser.error(str(exc))

compact = lambda value: json.dumps(value, separators=(",", ":"))
server_command = [
    "python3", "-m", "sglang.launch_server",
    "--model-path", deployment["checkpoint"],
    "--tokenizer-path", deployment["checkpoint"],
    "--revision", deployment["revision"],
    "--served-model-name", deployment["served_model"],
    "--context-length", str(deployment["context_length"]),
    "--tp-size", str(server["tensor_parallel_size"]),
    "--enable-multimodal",
    "--limit-mm-data-per-request", compact(server["limit_mm_data_per_request"]),
    "--max-running-requests", str(deployment["max_running_requests"]),
    "--cuda-graph-max-bs-decode", str(server["cuda_graph_max_bs_decode"]),
    "--attention-backend", server["attention_backend"],
    "--kv-cache-dtype", server["kv_cache_dtype"],
    "--mamba-ssm-dtype", server["mamba_ssm_dtype"],
    "--mamba-radix-cache-strategy", server["mamba_radix_cache_strategy"],
    "--max-mamba-cache-size", str(server["max_mamba_cache_size"]),
    "--chunked-prefill-size", str(server["chunked_prefill_size"]),
    "--mem-fraction-static", str(server["mem_fraction_static"]),
    "--reasoning-parser", server["reasoning_parser"],
    "--default-chat-template-kwargs", compact(server["default_chat_template_kwargs"]),
    "--host", server["host"], "--port", str(server["port"]),
]
if "max_total_tokens" in server:
    server_command.extend(["--max-total-tokens", str(server["max_total_tokens"])])
if server.get("constrained_json_disable_any_whitespace"):
    server_command.extend(["--grammar-backend", "xgrammar", "--constrained-json-disable-any-whitespace"])
command = [
    "docker", "run", "--rm", "--name", args.name,
    "--platform", runtime["platform"], "--gpus", "device=" + args.gpu,
    "--network", "host", "--shm-size", "8g",
    "--mount", "type=bind,source=" + str(cache_dir) + ",target=/model-cache",
    "--env", "HF_HOME=/model-cache", "--env", "HF_HUB_DISABLE_XET=1",
    runtime["image"], *server_command,
]
if args.inside_container:
    command = ["env", "HF_HOME=" + str(cache_dir), "HF_HUB_DISABLE_XET=1", *server_command]
print("Deployment: " + deployment["id"])
print("Model: " + deployment["checkpoint"] + " @ " + deployment["revision"])
print("Endpoint: http://" + server["host"] + ":" + str(server["port"]) + "/v1")
print(shlex.join(command))
if args.check:
    print("Static check passed. No GPU, Docker image or model weights were loaded.")
    sys.exit(0)

if sys.platform != "linux":
    parser.error("Run this command on the Linux GPU host; use --check locally")
if args.inside_container:
    if (os.environ.get("SGLANG_BUILD_COMMIT") != runtime["commit"]
            or os.environ.get("CUDA_VERSION") != runtime["cuda"]):
        parser.error("--inside-container requires the pinned image from the deployment manifest; its build/CUDA environment does not match")
for executable in (("nvidia-smi",) if args.inside_container else ("docker", "nvidia-smi")):
    if shutil.which(executable) is None:
        parser.error(executable + " is required on the GPU host")
try:
    gpu_info = subprocess.run([
        "nvidia-smi", "--id=" + args.gpu,
        "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader",
    ], check=True, capture_output=True, text=True)
    rows = list(csv.reader(gpu_info.stdout.strip().splitlines()))
    if len(rows) != 1 or len(rows[0]) != 3:
        raise ValueError("Could not read one GPU's NVIDIA driver version")
    driver = rows[0][1].strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", driver):
        raise ValueError("Could not parse NVIDIA driver version: " + driver)
    actual_version = tuple(int(p) for p in driver.split("."))
    actual_version += (0,) * (3 - len(actual_version))
    required_version = tuple(int(p) for p in runtime["minimum_linux_driver"].split("."))
    if actual_version < required_version:
        raise ValueError(
            "NVIDIA driver " + driver + " is too old for this CUDA " + runtime["cuda"]
            + " pilot. Use a GPU host with Linux driver >= " + runtime["minimum_linux_driver"]
            + ". No container was pulled, no model was loaded, and no driver was changed."
        )
    print("GPU: " + gpu_info.stdout.strip())
    if not args.inside_container:
        subprocess.run(["docker", "info", "--format", "{{.OSType}}"], check=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
except (OSError, ValueError, subprocess.CalledProcessError) as exc:
    parser.error(str(exc))
print("Starting the pinned CUDA " + runtime["cuda"] + " container. The host driver must support it.", flush=True)
os.execvp(command[0], command)
PY
