"""
Lium Python SDK

A clean, functional SDK for managing Celium Compute GPU pods programmatically.
Provides all functionality available in the Lium CLI.
"""

import os
import re
import json
import time
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime, timezone

import requests
import paramiko


@dataclass
class PodInfo:
    """Information about a pod."""
    id: str
    name: str
    status: str
    huid: str
    ssh_cmd: Optional[str]
    ports: Dict[str, int]
    created_at: str
    updated_at: str
    executor: Dict[str, Any]
    template: Dict[str, Any]


@dataclass
class ExecutorInfo:
    """Information about an executor."""
    id: str
    huid: str
    machine_name: str
    gpu_type: str
    gpu_count: int
    price_per_hour: float
    price_per_gpu_hour: float
    location: Dict[str, str]
    specs: Dict[str, Any]
    status: str


class Lium:
    """
    Lium SDK for managing Celium Compute GPU pods.
    
    Example usage:
        # Initialize
        from lium import Lium
        lium = Lium(api_key="your-api-key")
        
        # List available pods
        all_pods = lium.ls()
        h100s = lium.ls(gpu_type="H100")
        
        # Start pods
        pod = lium.up(executor_id="executor-uuid", pod_name="my-pod")
        
        # List active pods
        my_pods = lium.ps()
        
        # Execute commands - accepts pod ID, name, HUID, or PodInfo object
        result = lium.exec(pod, command="nvidia-smi")
        result = lium.exec("my-pod", command="nvidia-smi")
        result = lium.exec("pod-uuid", command="nvidia-smi")
        
        # Transfer files - accepts pod ID, name, HUID, or PodInfo object
        lium.scp("my-pod", local_path="./file.txt", remote_path="/home/file.txt")
        
        # Stop pods - accepts pod ID, name, HUID, or PodInfo object
        lium.down("my-pod")
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://celiumcompute.ai/api"):
        """
        Initialize Lium SDK.
        
        Args:
            api_key: API key for authentication. If None, will try to get from environment or config.
            base_url: Base URL for the API
        """
        self.api_key = api_key or self._get_api_key()
        self.base_url = base_url
        self.headers = {"X-API-KEY": self.api_key}
        self._ssh_key_path = None
        
        if not self.api_key:
            raise ValueError("API key is required. Set LIUM_API_KEY environment variable or pass api_key parameter.")
    
    def _get_api_key(self) -> Optional[str]:
        """Get API key from environment or config file."""
        # Import locally to avoid circular dependencies
        from .config import get_api_key
        return get_api_key()
    
    def _generate_huid(self, executor_id: str) -> str:
        """Generate human-readable ID from executor ID."""
        # Import locally to avoid circular dependencies
        from .helpers import generate_human_id
        return generate_human_id(executor_id)
    
    def _extract_gpu_type(self, machine_name: str) -> str:
        """Extract GPU model from machine name."""
        # Import locally to avoid circular dependencies
        from .helpers import extract_gpu_model
        return extract_gpu_model(machine_name)
    
    def _resolve_pod(self, pod: Union[str, PodInfo]) -> PodInfo:
        """
        Resolve pod identifier to PodInfo object.
        
        Args:
            pod: Pod ID, name, HUID, or PodInfo object
            
        Returns:
            PodInfo object
            
        Raises:
            ValueError: If pod not found
        """
        if isinstance(pod, PodInfo):
            return pod
        
        # It's a string identifier - search by ID, name, or HUID
        pods = self.ps()
        found_pod = next((p for p in pods if p.id == pod or p.name == pod or p.huid == pod), None)
        
        if not found_pod:
            raise ValueError(f"Pod '{pod}' not found")
        
        return found_pod
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request to API."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = requests.request(method, url, headers=self.headers, **kwargs)
        response.raise_for_status()
        return response
    
    # Core API Methods
    
    def ls(self, gpu_type: Optional[str] = None) -> List[ExecutorInfo]:
        """
        List available executors.
        
        Args:
            gpu_type: Filter by GPU type (e.g., "H100", "4090")
            
        Returns:
            List of ExecutorInfo objects
        """
        response = self._make_request("GET", "/executors")
        executors_data = response.json()
        
        executors = []
        for exec_data in executors_data:
            gpu_count = exec_data.get("specs", {}).get("gpu", {}).get("count", 1)
            machine_name = exec_data.get("machine_name", "")
            extracted_gpu_type = self._extract_gpu_type(machine_name)
            
            # Filter by GPU type if specified
            if gpu_type and extracted_gpu_type.upper() != gpu_type.upper():
                continue
            
            executor = ExecutorInfo(
                id=exec_data.get("id", ""),
                huid=self._generate_huid(exec_data.get("id", "")),
                machine_name=machine_name,
                gpu_type=extracted_gpu_type,
                gpu_count=gpu_count,
                price_per_hour=exec_data.get("price_per_hour", 0),
                price_per_gpu_hour=exec_data.get("price_per_hour", 0) / gpu_count if gpu_count > 0 else 0,
                location=exec_data.get("location", {}),
                specs=exec_data.get("specs", {}),
                status=exec_data.get("status", "unknown")
            )
            executors.append(executor)
        
        return executors
    
    def ps(self) -> List[PodInfo]:
        """
        List active pods.
        
        Returns:
            List of PodInfo objects
        """
        response = self._make_request("GET", "/pods")
        pods_data = response.json()
        
        pods = []
        for pod_data in pods_data:
            pod = PodInfo(
                id=pod_data.get("id", ""),
                name=pod_data.get("pod_name", ""),
                status=pod_data.get("status", "unknown"),
                huid=self._generate_huid(pod_data.get("id", "")),
                ssh_cmd=pod_data.get("ssh_connect_cmd"),
                ports=pod_data.get("ports_mapping", {}),
                created_at=pod_data.get("created_at", ""),
                updated_at=pod_data.get("updated_at", ""),
                executor=pod_data.get("executor", {}),
                template=pod_data.get("template", {})
            )
            pods.append(pod)
        
        return pods
    
    def get_templates(self) -> List[Dict[str, Any]]:
        """
        Get available templates.
        
        Returns:
            List of template dictionaries
        """
        response = self._make_request("GET", "/templates")
        return response.json()
    
    def up(self, executor_id: str, pod_name: str = None, template_id: Optional[str] = None, 
                  ssh_public_keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Start a new pod on an executor.
        
        Args:
            executor_id: UUID of the executor
            pod_name: Name for the pod
            template_id: UUID of template to use. If None, uses first available template.
            ssh_public_keys: List of SSH public keys. If None, tries to load from config.
            
        Returns:
            Pod information dictionary
        """
        if not template_id:
            templates = self.get_templates()
            if not templates:
                raise ValueError("No templates available")
            template_id = templates[0]["id"]
        
        if not ssh_public_keys:
            ssh_public_keys = self._get_ssh_public_keys()
        
        if not ssh_public_keys:
            raise ValueError("No SSH public keys found. Configure ssh.key_path or provide ssh_public_keys parameter.")
        
        payload = {
            "pod_name": pod_name,
            "template_id": template_id,
            "user_public_key": ssh_public_keys
        }
        
        # Get initial pod list to compare after creation
        initial_pods = {p.name: p.id for p in self.ps()}
        
        response = self._make_request("POST", f"/executors/{executor_id}/rent", json=payload)
        api_response = response.json()
        
        # If API response contains pod info, return it
        if api_response and 'id' in api_response:
            return api_response
        
        # Otherwise, find the newly created pod by comparing pod lists
        # Wait a moment for the pod to appear
        time.sleep(2)
        
        current_pods = self.ps()
        for pod in current_pods:
            if pod.name == pod_name and pod.name not in initial_pods:
                return {
                    'id': pod.id,
                    'name': pod.name,
                    'status': pod.status,
                    'huid': pod.huid,
                    'ssh_cmd': pod.ssh_cmd,
                    'executor_id': executor_id
                }
        
        # If we still can't find it, return what we have
        return api_response or {'name': pod_name, 'executor_id': executor_id}
    
    def down(self, pod: Optional[Union[str, PodInfo]] = None, executor_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Stop a pod.
        
        Args:
            pod: Pod ID, name, HUID, or PodInfo object to stop
            executor_id: Executor ID (if pod not provided)
            
        Returns:
            API response
        """
        if pod:
            pod_info = self._resolve_pod(pod)
            executor_id = pod_info.executor.get("id")
        
        if not executor_id:
            raise ValueError("Either pod or executor_id must be provided")
        
        response = self._make_request("DELETE", f"/executors/{executor_id}/rent")
        return response.json()
    
    # SSH and Execution Methods
    
    def _get_ssh_private_key_path(self) -> Optional[Path]:
        """Get SSH private key path from config."""
        if self._ssh_key_path:
            return self._ssh_key_path
        
        # Import locally to avoid circular dependencies
        from .config import get_config_value
        
        key_path = get_config_value("ssh.key_path")
        if key_path:
            # Remove .pub extension if present
            key_path = key_path.rstrip('.pub')
            self._ssh_key_path = Path(key_path).expanduser()
            return self._ssh_key_path
        
        # Try common SSH key locations
        for key_name in ["id_rsa", "id_ed25519", "id_ecdsa"]:
            key_path = Path.home() / ".ssh" / key_name
            if key_path.exists():
                self._ssh_key_path = key_path
                return self._ssh_key_path
        
        return None
    
    def _get_ssh_public_keys(self) -> List[str]:
        """Get SSH public keys from config."""
        # Import locally to avoid circular dependencies
        from .config import get_ssh_public_keys
        return get_ssh_public_keys()
    
    def _get_ssh_connection_info(self, pod: Union[str, PodInfo]) -> Tuple[str, str, int]:
        """Get SSH connection info for a pod."""
        pod_info = self._resolve_pod(pod)
        
        if not pod_info.ssh_cmd:
            raise ValueError(f"Pod {pod_info.name} has no SSH connection available")
        
        # Parse SSH command: "ssh user@host -p port"
        import shlex
        parts = shlex.split(pod_info.ssh_cmd)
        user_host = parts[1]
        user, host = user_host.split('@')
        
        port = 22
        if "-p" in parts:
            port_index = parts.index("-p") + 1
            if port_index < len(parts):
                port = int(parts[port_index])
        
        return user, host, port
    
    def exec(self, pod: Union[str, PodInfo], command: str, env_vars: Optional[Dict[str, str]] = None,
                       timeout: int = 30) -> Dict[str, Any]:
        """
        Execute a command on a pod via SSH.
        
        Args:
            pod: Pod ID, name, HUID, or PodInfo object
            command: Command to execute
            env_vars: Environment variables to set
            timeout: SSH connection timeout
            
        Returns:
            Dictionary with stdout, stderr, exit_code
        """
        private_key_path = self._get_ssh_private_key_path()
        if not private_key_path or not private_key_path.exists():
            raise ValueError("SSH private key not found. Configure ssh.key_path in ~/.lium/config.ini")
        
        user, host, port = self._get_ssh_connection_info(pod)
        
        # Prepare command with environment variables
        if env_vars:
            env_exports = ' && '.join([f'export {k}="{v}"' for k, v in env_vars.items()])
            command = f"{env_exports} && {command}"
        
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            # Load SSH key
            key_types = [paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey]
            loaded_key = None
            
            for key_type in key_types:
                try:
                    loaded_key = key_type.from_private_key_file(str(private_key_path))
                    break
                except paramiko.ssh_exception.SSHException:
                    continue
            
            if not loaded_key:
                raise ValueError("Could not load SSH private key")
            
            ssh_client.connect(hostname=host, port=port, username=user, pkey=loaded_key, timeout=timeout)
            stdin, stdout, stderr = ssh_client.exec_command(command)
            
            stdout_text = stdout.read().decode('utf-8', errors='replace')
            stderr_text = stderr.read().decode('utf-8', errors='replace')
            exit_code = stdout.channel.recv_exit_status()
            
            return {
                "stdout": stdout_text,
                "stderr": stderr_text,
                "exit_code": exit_code,
                "success": exit_code == 0
            }
        
        finally:
            ssh_client.close()
    
    def scp(self, pod: Union[str, PodInfo], local_path: str, remote_path: str, timeout: int = 30) -> None:
        """
        Upload a file to a pod via SFTP.
        
        Args:
            pod: Pod ID, name, HUID, or PodInfo object
            local_path: Local file path
            remote_path: Remote file path
            timeout: Connection timeout
        """
        private_key_path = self._get_ssh_private_key_path()
        if not private_key_path or not private_key_path.exists():
            raise ValueError("SSH private key not found")
        
        user, host, port = self._get_ssh_connection_info(pod)
        
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            # Load SSH key
            key_types = [paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey]
            loaded_key = None
            
            for key_type in key_types:
                try:
                    loaded_key = key_type.from_private_key_file(str(private_key_path))
                    break
                except paramiko.ssh_exception.SSHException:
                    continue
            
            if not loaded_key:
                raise ValueError("Could not load SSH private key")
            
            ssh_client.connect(hostname=host, port=port, username=user, pkey=loaded_key, timeout=timeout)
            sftp = ssh_client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
        
        finally:
            ssh_client.close()
    
    def download_file(self, pod: Union[str, PodInfo], remote_path: str, local_path: str, timeout: int = 30) -> None:
        """
        Download a file from a pod via SFTP.
        
        Args:
            pod: Pod ID, name, HUID, or PodInfo object
            remote_path: Remote file path
            local_path: Local file path
            timeout: Connection timeout
        """
        private_key_path = self._get_ssh_private_key_path()
        if not private_key_path or not private_key_path.exists():
            raise ValueError("SSH private key not found")
        
        user, host, port = self._get_ssh_connection_info(pod)
        
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            # Load SSH key
            key_types = [paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey]
            loaded_key = None
            
            for key_type in key_types:
                try:
                    loaded_key = key_type.from_private_key_file(str(private_key_path))
                    break
                except paramiko.ssh_exception.SSHException:
                    continue
            
            if not loaded_key:
                raise ValueError("Could not load SSH private key")
            
            ssh_client.connect(hostname=host, port=port, username=user, pkey=loaded_key, timeout=timeout)
            sftp = ssh_client.open_sftp()
            sftp.get(remote_path, local_path)
            sftp.close()
        
        finally:
            ssh_client.close()
    
    def sync_directory(self, pod: Union[str, PodInfo], local_path: str, remote_path: str, 
                      direction: str = "up", delete: bool = False, exclude: Optional[List[str]] = None) -> bool:
        """
        Sync directories using rsync.
        
        Args:
            pod: Pod ID, name, HUID, or PodInfo object
            local_path: Local directory path
            remote_path: Remote directory path
            direction: "up" (local to remote) or "down" (remote to local)
            delete: Delete extraneous files
            exclude: List of patterns to exclude
            
        Returns:
            True if successful
        """
        private_key_path = self._get_ssh_private_key_path()
        if not private_key_path or not private_key_path.exists():
            raise ValueError("SSH private key not found")
        
        user, host, port = self._get_ssh_connection_info(pod)
        
        # Build rsync command
        rsync_cmd = [
            "rsync", "-avz",
            "-e", f"ssh -i {private_key_path} -p {port} -o StrictHostKeyChecking=no"
        ]
        
        if delete:
            rsync_cmd.append("--delete")
        
        if exclude:
            for pattern in exclude:
                rsync_cmd.extend(["--exclude", pattern])
        
        if direction == "up":
            rsync_cmd.extend([local_path, f"{user}@{host}:{remote_path}"])
        else:
            rsync_cmd.extend([f"{user}@{host}:{remote_path}", local_path])
        
        try:
            result = subprocess.run(rsync_cmd, capture_output=True, text=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Rsync failed: {e.stderr}")
    
    # Utility Methods
    
    def wait_for_pod_ready(self, pod: Union[str, PodInfo], max_wait: int = 300, check_interval: int = 10) -> bool:
        """
        Wait for a pod to be ready.
        
        Args:
            pod: Pod ID, name, HUID, or PodInfo object
            max_wait: Maximum wait time in seconds
            check_interval: Check interval in seconds
            
        Returns:
            True if pod is ready, False if timeout
        """
        pod_info = self._resolve_pod(pod)
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            pods = self.ps()
            current_pod = next((p for p in pods if p.id == pod_info.id), None)
            
            if current_pod and current_pod.status.upper() == "RUNNING" and current_pod.ssh_cmd:
                return True
            
            time.sleep(check_interval)
        
        return False
    
    def get_pod_by_name(self, name: str) -> Optional[PodInfo]:
        """Get pod by name or HUID."""
        pods = self.ps()
        return next((p for p in pods if p.name == name or p.huid == name), None)
    
    def get_executor_by_huid(self, huid: str) -> Optional[ExecutorInfo]:
        """Get executor by HUID."""
        executors = self.ls()
        return next((e for e in executors if e.huid == huid), None)


# Convenience functions

def init(api_key: Optional[str] = None) -> Lium:
    """Create a Lium SDK client."""
    return Lium(api_key=api_key)


def list_gpu_types(api_key: Optional[str] = None) -> List[str]:
    """Get list of available GPU types."""
    client = Lium(api_key=api_key)
    executors = client.ls()
    return list(set(e.gpu_type for e in executors)) 