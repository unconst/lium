"""
Provision provider for instance management.

This module provides a thin imperative wrapper around the existing LiumSDK
to enable context-managed SSH sessions and simplified instance workflows.
"""

import contextlib
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional

from .sdk import LiumSDK, PodInfo


@dataclass
class SSHResult:
    """Result of an SSH command execution with imperative error handling."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    success: bool

    @classmethod
    def from_sdk_result(cls, command: str, sdk_result: Dict) -> "SSHResult":
        """Create from SDK execute_command result."""
        return cls(
            command=command,
            exit_code=sdk_result.get("exit_code", -1),
            stdout=sdk_result.get("stdout", ""),
            stderr=sdk_result.get("stderr", ""),
            success=sdk_result.get("success", False),
        )

    def raise_on_error(self) -> "SSHResult":
        """Raise exception if command failed."""
        if not self.success:
            raise RuntimeError(
                f"Command failed (exit {self.exit_code}): {self.command}\nstderr: {self.stderr}"
            )
        return self


class InstanceWithContext:
    """Wrapper around PodInfo with imperative SSH context manager."""

    def __init__(self, pod_info: PodInfo, sdk: LiumSDK):
        self.pod_info = pod_info
        self.sdk = sdk

    @property
    def id(self) -> str:
        return self.pod_info.id

    @property
    def name(self) -> str:
        return self.pod_info.name

    @property
    def status(self) -> str:
        return self.pod_info.status

    @contextlib.contextmanager
    def ssh(self) -> Iterator["SSHContext"]:
        """Get imperative SSH context manager."""
        yield SSHContext(self.pod_info.id, self.sdk)

    def stop(self) -> None:
        """Stop the instance."""
        self.sdk.stop_pod(pod_id=self.id)


class SSHContext:
    """Context for executing SSH commands imperatively."""

    def __init__(self, pod_id: str, sdk: LiumSDK):
        self.pod_id = pod_id
        self.sdk = sdk

    def run(
        self, command: str, env_vars: Optional[Dict[str, str]] = None, timeout: int = 300
    ) -> SSHResult:
        """Execute command and return imperative result."""
        sdk_result = self.sdk.execute_command(
            pod_id=self.pod_id, command=command, env_vars=env_vars, timeout=timeout
        )
        return SSHResult.from_sdk_result(command, sdk_result)

    def upload(self, local_path: str, remote_path: str, timeout: int = 30) -> None:
        """Upload file to remote instance."""
        self.sdk.upload_file(
            pod_id=self.pod_id, local_path=local_path, remote_path=remote_path, timeout=timeout
        )

    def download(self, remote_path: str, local_path: str, timeout: int = 30) -> None:
        """Download file from remote instance."""
        self.sdk.download_file(
            pod_id=self.pod_id, remote_path=remote_path, local_path=local_path, timeout=timeout
        )

    def sync(
        self,
        local_path: str,
        remote_path: str,
        direction: str = "up",
        delete: bool = False,
        exclude: Optional[List[str]] = None,
    ) -> None:
        """Sync directories using rsync."""
        success = self.sdk.sync_directory(
            pod_id=self.pod_id,
            local_path=local_path,
            remote_path=remote_path,
            direction=direction,
            delete=delete,
            exclude=exclude,
        )
        if not success:
            raise RuntimeError(f"Rsync failed for {direction} sync: {local_path} <-> {remote_path}")

    def port_forward(self, local_port: int, remote_port: int) -> "PortForward":
        """Create port forward tunnel."""
        return PortForward(self.pod_id, self.sdk, local_port, remote_port)


class PortForward:
    """Port forwarding tunnel management."""

    def __init__(self, pod_id: str, sdk: LiumSDK, local_port: int, remote_port: int):
        self.pod_id = pod_id
        self.sdk = sdk
        self.local_port = local_port
        self.remote_port = remote_port
        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None

    def __enter__(self) -> "PortForward":
        """Start port forwarding."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stop port forwarding."""
        self.stop()

    def start(self) -> None:
        """Start the port forwarding tunnel."""
        if self._process:
            return

        user, host, port = self.sdk._get_ssh_connection_info(self.pod_id)
        private_key_path = self.sdk._get_ssh_private_key_path()

        if not private_key_path or not private_key_path.exists():
            raise ValueError("SSH private key not found")

        ssh_cmd = [
            "ssh",
            "-i",
            str(private_key_path),
            "-p",
            str(port),
            "-L",
            f"{self.local_port}:localhost:{self.remote_port}",
            "-N",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "LogLevel=ERROR",
            f"{user}@{host}",
        ]

        self._process = subprocess.Popen(
            ssh_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL
        )

        time.sleep(1)

        if self._process.poll() is not None:
            stderr = self._process.stderr.read().decode() if self._process.stderr else ""
            raise RuntimeError(f"Port forward failed to start: {stderr}")

    def stop(self) -> None:
        """Stop the port forwarding tunnel."""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    @property
    def is_active(self) -> bool:
        """Check if port forward is active."""
        return self._process is not None and self._process.poll() is None


class LiumPodClient:
    """Lightweight client for imperative instance management."""

    def __init__(self, api_key: Optional[str] = None):
        self.sdk = LiumSDK(api_key=api_key)

    def start_instance(
        self, executor_id: Optional[str] = None, instance_name: Optional[str] = None
    ) -> InstanceWithContext:
        """Start instance and return imperative wrapper. If instance with same name exists, return that."""
        if not instance_name:
            import time

            instance_name = f"instance-{int(time.time())}"

        pods = self.sdk.list_pods()
        existing_pod = next((p for p in pods if p.name == instance_name), None)
        if existing_pod:
            return InstanceWithContext(existing_pod, self.sdk)

        if not executor_id:
            executors = self.sdk.list_executors()
            if not executors:
                raise RuntimeError("No executors available")
            executor_id = executors[0].id

        self.sdk.start_pod(executor_id=executor_id, pod_name=instance_name)

        pods = self.sdk.list_pods()
        pod_info = next((p for p in pods if p.name == instance_name), None)
        if not pod_info:
            raise RuntimeError(f"Could not find started pod: {instance_name}")

        if not self.sdk.wait_for_pod_ready(pod_info.id, max_wait=300):
            raise RuntimeError(f"Pod {pod_info.id} did not become ready")

        return InstanceWithContext(pod_info, self.sdk)

    def list_instances(self) -> List[InstanceWithContext]:
        """List all instances as imperative wrappers."""
        pods = self.sdk.list_pods()
        return [InstanceWithContext(pod, self.sdk) for pod in pods]
