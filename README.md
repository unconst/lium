# 𓋼 Lium 

TAO + LIUM = GPU

Manage [Celium](https://celiumcompute.ai) GPU pods from your terminal.

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

### Use

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
# Rent pod with HUID
lium up noble-matrix-a3
# Rent multiple pods
lium up golden-pixel-2f, calm-jaguar-f6
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
## License

2025 Yuma Rao

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Commands

### `lium rsync` - Sync Directories with Pods

The `lium rsync` command provides powerful directory synchronization capabilities between your local machine and running pods using rsync. It supports bidirectional sync, multiple pod operations, and comprehensive rsync options.

#### Basic Usage

```bash
# Sync local directory to multiple pods
lium rsync ~/project/ 1,2:/home/project/

# Sync from pod to local directory  
lium rsync 1:/home/project/ ~/backup/

# Sync from all pods to local directory
lium rsync all:/home/logs/ ~/collected/

# Sync with options
lium rsync ~/data/ all:/workspace/ --delete --exclude '*.tmp' --progress
```

#### Path Formats

**Local paths:**
- `/path/to/dir/` - Absolute path
- `~/myproject/` - Home directory relative path
- `./relative/` - Relative to current directory

**Remote paths:**
- `pod_targets:/path/to/dir/` - Remote path on pods

**Pod targets** can be:
- Pod HUIDs: `zesty-orbit-08:/path/`
- Index numbers from `lium ps`: `1:/path/`, `2:/path/`
- Comma-separated: `1,2:/path/` (syncs with multiple pods)
- All pods: `all:/path/`

#### Options

| Option | Description |
|--------|-------------|
| `--delete` | Delete extraneous files from destination dirs (use with caution) |
| `--exclude PATTERN` | Exclude files matching pattern. Can be used multiple times |
| `--dry-run, -n` | Show what would be transferred without making changes |
| `--archive, -a` | Archive mode (preserves permissions, times, etc). **Enabled by default** |
| `--verbose, -v` | Increase verbosity of rsync output |
| `--compress, -z` | Compress file data during the transfer |
| `--retry-attempts N` | Number of retry attempts on failure (default: 3) |
| `--progress` | Show progress during transfer |

#### Examples

**Development Workflow:**
```bash
# Initial sync of project to pods
lium rsync ~/myproject/ all:/workspace/myproject/ --progress

# Incremental updates during development
lium rsync ~/myproject/ 1,2:/workspace/myproject/ --exclude '*.pyc' --exclude '__pycache__'

# Collect results from all pods
lium rsync all:/workspace/results/ ~/results/ --dry-run  # Check first
lium rsync all:/workspace/results/ ~/results/
```

**Data Management:**
```bash
# Backup logs from all pods
lium rsync all:/var/log/myapp/ ~/backups/logs/

# Distribute datasets to pods
lium rsync ~/datasets/ all:/data/ --compress --progress

# Clean sync (remove files not in source)
lium rsync ~/config/ all:/app/config/ --delete
```

#### Advanced Features

**Fault Tolerance:**
- Automatic retry on transient failures (configurable with `--retry-attempts`)
- Continues with other pods if one fails
- Validates paths before starting operations
- Intelligent error detection (skips retries for permission errors)

**Multiple Pod Operations:**
- Sync to/from multiple pods simultaneously
- Individual success/failure tracking per pod
- Comprehensive operation summary

**Safety Features:**
- Dry-run mode to preview changes
- Archive mode enabled by default (preserves permissions, timestamps, etc.)
- Path validation before operations
- Clear error messages and warnings

#### Important Notes

1. **Trailing Slashes Matter**: 
   - `~/project/` syncs the *contents* of project directory
   - `~/project` syncs the project directory itself

2. **Prerequisites**:
   - `rsync` must be installed on your system
   - SSH key must be configured: `lium config set ssh.key_path /path/to/key`
   - Pods must be in RUNNING state

3. **Limitations**:
   - Remote-to-remote sync between pods not currently supported
   - Use local intermediate directory for pod-to-pod transfers

4. **Performance**:
   - Use `--compress` for slow networks
   - Use `--progress` to monitor large transfers
   - Archive mode (`-a`) is enabled by default for data integrity
