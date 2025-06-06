"""Lium - Manage Celium GPU pods from your terminal and Python scripts."""

__version__ = "0.2.0"

# Expose SDK components at package level
from .sdk import (
    LiumSDK,
    PodInfo,
    ExecutorInfo,
    create_client,
    list_gpu_types
)

# Expose API client for direct use
from .api import LiumAPIClient

__all__ = [
    "LiumSDK",
    "PodInfo", 
    "ExecutorInfo",
    "create_client",
    "list_gpu_types",
    "LiumAPIClient"
] 