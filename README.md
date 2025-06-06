# 𓋼 Lium 

TAO + LIUM = GPU

Manage [Celium](https://celiumcompute.ai) GPU pods from your terminal and Python scripts.

---
### Install 
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
# Clone Lium
git clone git@github.com:unconst/lium.git && cd lium
# Install from source 
uv venv && source .venv/bin/activate && uv pip install -e .
```

## CLI Usage

---
`lium init` 
```bash
# Init lium config
lium init
> Please enter your Lium API key (See: https://celiumcompute.ai/api-keys): ...
> Please enter the path to your ssh public key (i.e.: ~/.ssh/id_rsa.pub): ...
```
![Lium config show](assets/liumconfigshow.png)

---
`lium fund` 
```bash
# Add TAO to balance
lium fund --wallet my_wallet_name --tao 10
```
![Lium fund](assets/liumfund.png)

---
`lium ls` 
```bash
# List all GPU types
lium ls 
# List available H100s
lium ls H100
```
![Lium ls H100](assets/liumls.png)

---
`lium up`
```bash
# Rent pod using index from ls
lium up 1
# Rent pod with HUID
lium up noble-matrix-a3
# Rent multiple pods from index and HUID.
lium up 1, calm-jaguar-f6
```
![Lium up](assets/liumuppod.png)

---
`lium ps`
```bash
# Shows all pods
lium ps 
# Inspect pod by HUID
lium ps cosmic-raven-39
# Inspect pod by index.
lium ps 2
```
![Lium ps](assets/liumps.png)

---
`lium exec`
```bash
# Run on pods 1, 2, 3
lium exec 1,2,3 "nvidia-smi" 
# Run on all pods
lium exec all "uptime"
# Execute with mixed targets.
lium exec 1,zesty-orbit-08 "ls -la"
# Execute with script
lium exec 1 --script "python script.py"
# Execute with env vars
lium exec 3 --env API_KEY=secret --script "script.sh"
# Execute jupyter notebook.
lium exec cosmic-raven-39 --script scripts/jupyter.sh
```
![lium exec](assets/jupyter.png)

---
`lium ssh`
```bash
# SSH to pod #1
lium ssh 1      
# SSH by HUID         
lium ssh zesty-orbit-08    
```
![lium ssh](assets/liumssh.png)

---
`lium scp`
```bash
# Copy to pods 1 and 2
lium scp 1,2 ~/file.txt 
# Wallet to all pods
lium scp all --coldkey A --hotkey B 
```
![lium exec](assets/liumscp.png)

---
`lium rsync`
```bash
# local to multiple pods (verbose)
lium rsync ~/project/ 1,2:/home/project/ -v
# pod to local (with compress)
lium rsync 1:/home/project/ ~/backup/ -z
# all pods to local
lium rsync all:/home/logs/ ~/collected/
# Delete extraneous files from destination dirs (use with caution).
lium rsync ~/data/ all:/workspace/ --delete --exclude '*.tmp'
```
![lium exec](assets/liumscp.png)

---
`lium down`
```bash
# Release rental by HUID
lium down golden-pixel-2f
# Release multiple rentals
lium down 1,2,3
# Release all rentals
lium down --all -y
```
![lium down](assets/liumdown.png)

---
`lium image`
```bash
# Build a custom image from local Dockerfile 
lium image my_image .
# Set image as default.
lium config set template.default_id 3f839fd6-1c7f-4b69-8850-9503a4c1c3f5
# Rent pod with image.
lium up golden-pixel-2f --image 3f839fd6-1c7f-4b69-8850-9503a4c1c3f5
```
![Lium image](assets/liumimage.png)
> NOTE: Dockerfiles **MUST** be based off of Datura offical images (i.e. FROM daturaai/dind:0.0.0 )

---
`lium config`
```bash
# Set your celium API key: (https://celiumcompute.ai/api-keys)
lium config set api.api_key <YOUR_API_KEY_HERE> 
# Set path to your ssh private key
lium config set ssh.key_path <PATH_TO_YOUR_SSH_PRIVATE_KEY>
# Select your default template
lium config set template.default_id 
# Show your config file in: ~/.lium/config.ini 
lium config show
```
![Lium config show](assets/liumconfigshow.png)

---

## Python SDK Usage

Lium also provides a comprehensive Python SDK for programmatic access to all CLI functionality:

```python
from lium import LiumSDK

# Initialize SDK (uses same config as CLI)
lium = LiumSDK()

# List available H100 executors
h100s = lium.list_executors(gpu_type="H100")
cheapest = min(h100s, key=lambda x: x.price_per_gpu_hour)

# Start a pod
pod = lium.start_pod(
    executor_id=cheapest.id,
    pod_name="my-training-job"
)

# Wait for pod to be ready
lium.wait_for_pod_ready(pod['id'])

# Execute commands
result = lium.execute_command(
    pod_id=pod['id'],
    command="nvidia-smi",
    env_vars={"CUDA_VISIBLE_DEVICES": "0"}
)

# Upload files
lium.upload_file(
    pod_id=pod['id'],
    local_path="./train.py", 
    remote_path="/home/train.py"
)

# Download results
lium.download_file(
    pod_id=pod['id'],
    remote_path="/home/model.pth",
    local_path="./model.pth"
)

# Stop pod when done
lium.stop_pod(pod_id=pod['id'])
```

### SDK Features

- **Same Configuration**: Uses the same `~/.lium/config.ini` as the CLI
- **Full Feature Parity**: All CLI commands available as Python methods
- **Type Safety**: Rich data classes for executors and pods
- **Error Handling**: Proper exception handling with meaningful messages
- **SSH Integration**: Automatic SSH key detection and connection handling

### SDK Installation

The SDK is included automatically when you install Lium:

```bash
uv pip install -e .
```

Then import and use:

```python
from lium import LiumSDK, PodInfo, ExecutorInfo
```

For detailed SDK documentation, see the included examples and docstrings.

---

## License

2025 Yuma Rao

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

