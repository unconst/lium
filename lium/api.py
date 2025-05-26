"""API client for interacting with Celium Compute API."""

import requests
from typing import List, Dict, Any, Optional


class LiumAPIClient:
    """Client for interacting with the Celium Compute API."""
    
    def __init__(self, api_key: str, base_url: str = "https://celiumcompute.ai/api"):
        """Initialize the API client.
        
        Args:
            api_key: API key for authentication
            base_url: Base URL for the API (default: https://celiumcompute.ai/api)
        """
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {"X-API-KEY": api_key}
    
    def get_executors(self) -> List[Dict[str, Any]]:
        """Fetch all available executors.
        
        Returns:
            List of executor dictionaries
            
        Raises:
            requests.RequestException: If the API request fails
        """
        url = f"{self.base_url}/executors"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json() 