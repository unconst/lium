"""Lium - Manage Celium GPU pods from your terminal and Python scripts."""

__version__ = "0.2.0"

# Expose SDK components at package level
# Expose API client for direct use
from .api import LiumAPIClient

# Expose provision provider components
from .provision import (
    InstanceWithContext,
    LiumPodClient,
    PortForward,
    SSHContext,
    SSHResult,
)
from .sdk import ExecutorInfo, LiumSDK, PodInfo, create_client, list_gpu_types

__all__ = [
    "LiumSDK",
    "PodInfo",
    "ExecutorInfo",
    "create_client",
    "list_gpu_types",
    "LiumAPIClient",
    "LiumPodClient",
    "InstanceWithContext",
    "SSHResult",
    "SSHContext",
    "PortForward",
]
