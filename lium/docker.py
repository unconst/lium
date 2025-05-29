

import docker
import os
from .api import LiumAPIClient
from rich.prompt import Prompt

from .config import (
    get_or_set_docker_credentials,
)
from .styles import get_theme, styled, SolarizedColors, MonochromeColors, style_manager, ColorScheme


def build_docker_image(image_name:str, dockerfilepath:str):
    
    user, password = get_or_set_docker_credentials()    
    image_tag = f"{user}/{image_name}:latest"

    # --- Docker Client Initialization ---
    try:
        client = docker.from_env()
    except docker.errors.DockerException:
        print("Error: Could not connect to Docker daemon. Is Docker running? Try starting Docker with 'systemctl start docker' or ensure the Docker Desktop is running.")
        exit(1)
        
    try:
        client.login(username=user, password=password)
        print("Login successful.")
    except docker.errors.APIError as e:
        print(f"Docker Hub login failed: {e}")
        print("Please ensure your DOCKER_USERNAME and DOCKER_PASSWORD (or Access Token) are correct.")
        exit(1)

    # --- Build Docker Image ---
    print(f"Building Docker image from Dockerfile: {os.getcwd()}/{dockerfilepath}Dockerfile")
    try:
        print ('As:', dockerfilepath, image_tag)
        image, build_log = client.images.build(
            path=dockerfilepath, 
            tag=image_tag, 
            rm=True, # Remove intermediate containers
            forcerm=True # Always remove intermediate containers, even if the build fails
        )
        print ('build donw')
        for log_line in build_log:
            print (log_line)

        print(f"Pushing image {image_tag} to Docker Hub...")
        push_log_gen = client.images.push(image_tag, stream=True, decode=True)
        digest = None
        for log_line in push_log_gen:
            if "status" in log_line:
                print(f"Push status: {log_line['status']}", end="")
                if "progress" in log_line:
                    print(f" - {log_line['progress']}", end="")
                if "id" in log_line:
                    print(f" (ID: {log_line['id']})", end="")
                print() # Newline after each status update
            if "status" in log_line and "digest" in log_line["status"]:
                digest = log_line["status"].split("digest: ")[1].split(" ")[0]
            elif "error" in log_line:
                print(f"Error during push: {log_line['errorDetail']['message']}")
            elif "aux" in log_line and "Digest" in log_line["aux"]:
                digest = log_line["aux"]["Digest"]
        
        if digest:
            print(f"Image digest: {digest}")
        print(f"Image {image_tag} pushed successfully to Docker Hub.")

    except docker.errors.BuildError as e:
        print(f"Error building Docker image: {e}")
        exit(1)
    except docker.errors.APIError as e:
        print(f"Error communicating with Docker API during build: {e}")
        exit(1)
    return digest