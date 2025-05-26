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

    def get_pods(self) -> List[Dict[str, Any]]:
        """Fetch all active pods for the authenticated user.

        Returns:
            List of pod dictionaries

        Raises:
            requests.RequestException: If the API request fails
        """
        url = f"{self.base_url}/pods"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def rent_pod(
        self, 
        executor_id: str, 
        pod_name: str, 
        template_id: str, 
        user_public_keys: List[str]
    ) -> Dict[str, Any]:
        """Rents a new pod on a specified executor.

        Args:
            executor_id: The UUID of the executor to rent the pod on.
            pod_name: A name for the pod.
            template_id: The UUID of the template to use for the pod.
            user_public_keys: A list of SSH public key strings.

        Returns:
            A dictionary representing the newly created pod.

        Raises:
            requests.RequestException: If the API request fails.
        """
        url = f"{self.base_url}/executors/{executor_id}/rent"
        payload = {
            "pod_name": pod_name,
            "template_id": template_id,
            "user_public_key": user_public_keys  # API expects "user_public_key"
        }
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status() # Will raise an HTTPError for bad responses (4xx or 5xx)
        return response.json()

    def get_templates(self) -> List[Dict[str, Any]]:
        """Fetch all available templates.

        Returns:
            List of template dictionaries.

        Raises:
            requests.RequestException: If the API request fails.
        """
        url = f"{self.base_url}/templates"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def unrent_pod(self, executor_id: str) -> Dict[str, Any]:
        """Unrents/stops a pod on a specified executor by making a DELETE request 
           to its /rent endpoint.

        Args:
            executor_id: The UUID of the executor hosting the pod to be unrented.

        Returns:
            API response, hopefully indicating success or failure.

        Raises:
            requests.RequestException: If the API request fails.
        """
        url = f"{self.base_url}/executors/{executor_id}/rent"
        print(url)
        
        response = requests.delete(url, headers=self.headers)
        response.raise_for_status() 
        return response.json() 