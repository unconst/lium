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
        
    def get_funding_wallets(self) -> List[str]:
        user = self.get_users_me()
        url = f"https://pay-api.celiumcompute.ai/wallet/available-wallets/{user['stripe_customer_id']}"
        headers = {"X-Api-Key": f"admin-test-key"}
        response = requests.get(url, headers=headers)
        return response.json()
        
    def get_users_me(self) -> Dict:
        url = "https://celiumcompute.ai//api/users/me"
        response = requests.get(url, headers=self.headers)
        return response.json()
        
    def get_access_key(self) -> str:
        """Fetch celium access key
        
        Returns:
            Celium access key.
            
        Raises:
            requests.RequestException: If the API request fails
        """
        url = "https://pay-api.celiumcompute.ai/token/generate"
        headers = {
            "X-Api-Key": f"admin-test-key"
        }
        response = requests.get(url, headers=headers)
        return response.json()['access_key']
    
    def get_app_id(self) -> str:        
        url = "https://celiumcompute.ai/api/tao/create-transfer"
        data = {
            "amount": 10,
        }
        response = requests.post(url, json=data, headers=self.headers)
        api_id = response.json()['url'].split('app_id=')[1].split('&')[0]
        return api_id
    
    def verify_access_key(
        self, 
        coldkey: str,
        access_key: str, 
        signature: str, 
    ) -> Dict[str, Any]:
        url = "https://pay-api.celiumcompute.ai/token/verify"
        headers = {"X-Api-Key": f"admin-test-key"}
        user = self.get_users_me()
        data = {
            "coldkey_address": coldkey,
            "access_key": access_key,
            "signature": signature,
            "stripe_customer_id": user['stripe_customer_id'],
            "application_id": self.get_app_id()
        }
        response = requests.post(url, headers=headers, json=data)
        return response
    
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
        print (url, payload)
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