#!/usr/bin/env bash
# Start SSH inside the pinned Qwen3.8 image on an existing RunPod network volume.
# This bootstraps access only; the model server is started separately after checks.
set -euo pipefail

if [[ "${1:-}" == "--check" ]]; then
    echo "RunPod start command: /bin/bash /workspace/qwen38-pod-bootstrap.sh"
    echo "Requires the existing public authorized_keys at /workspace/qwen38-pod-authorized_keys."
    echo "No packages installed, files written, or services started."
    exit 0
fi

if [[ "$EUID" != 0 || ! -d /workspace ]]; then
    echo "Run as root in the GPU pod with the network volume mounted at /workspace." >&2
    exit 1
fi
if [[ ! -s /workspace/qwen38-pod-authorized_keys ]]; then
    echo "Missing preserved SSH public keys; do not start with an empty key file." >&2
    exit 1
fi

exec > >(tee -a /workspace/qwen38-pod-bootstrap.log) 2>&1
echo "Starting SSH bootstrap at $(date -u +%FT%TZ)"
export DEBIAN_FRONTEND=noninteractive
if [[ ! -x /usr/sbin/sshd ]]; then
    apt-get update
    apt-get install -y --no-install-recommends openssh-server
fi

install -d -m 0700 /root/.ssh
install -m 0600 /workspace/qwen38-pod-authorized_keys /root/.ssh/authorized_keys
install -d -m 0755 /run/sshd /etc/ssh/sshd_config.d
# Some inference images contain build-time host keys. Use a fresh key for this pod.
if [[ ! -f /etc/ssh/qwen38_host_ed25519_key ]]; then
    ssh-keygen -q -t ed25519 -N '' -f /etc/ssh/qwen38_host_ed25519_key
fi
cat > /etc/ssh/sshd_config.d/00-qwen38-pod.conf <<'SSHD_CONFIG'
HostKey /etc/ssh/qwen38_host_ed25519_key
PubkeyAuthentication yes
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
SSHD_CONFIG
/usr/sbin/sshd -t
echo "SSH configuration checked; starting the SSH server. Model loading remains separate."
exec /usr/sbin/sshd -D -e
