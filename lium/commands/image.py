"""Docker image creation command for Lium CLI."""

import click
import time

from ..config import get_or_set_api_key
from ..api import LiumAPIClient
from ..styles import styled
from ..helpers import *


@click.command(name="image")
@click.argument("image_name", required=True, type=str)
@click.argument("path", required=True, type=str)
def image_command(image_name: str, path: str):
    api_key = get_or_set_api_key()
    client = LiumAPIClient(api_key)
    digest = build_docker_image(image_name, path)
    client.post_image(
        image_name=image_name,
        digest=digest,
        tag='latest'
    )
    exists = False
    templates = client.get_templates()
    for temp in templates:
        if temp['docker_image_digest'] == digest:
            exists = True
    if not exists:
        console.print(styled('Failed to upload image to Celium, try again later.', "info"))
        exit(1)
    start = time.time()
    while True:
        templates = client.get_templates()
        for temp in templates:
            if temp['docker_image_digest'] == digest:
                break
        if temp['status'] == 'VERIFY_SUCCESS':
            console.print(styled(f"Image is verified.\nUse it lium up <pod> --image {temp['id']}", "info"))
            break
        else:
            console.print(styled(f"Status: {temp['docker_image_digest']}, Elapsed: {int(time.time() - start)}s ", "info"))
            time.sleep(10)
            continue 