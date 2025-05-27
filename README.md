# Lium CLI 🚀

CLI for  [CeliumCompute.ai](https://celiumcompute.ai).

---

**Lium CLI** empowers you to effortlessly list, launch, and manage high-performance GPU executors directly from your terminal. 

### 1. Installation

Make sure you have Python 3.10+ installed.

```bash
# Recommended: Install with uv (super fast Python package installer)
# If you don't have uv: pip install uv
uv pip install lium

# Or, using pip directly:
pip install lium
```

(For development, clone this repository and run `uv pip install -e .` in the project directory.)

### 2. Get Your API Key

You'll need an API key from [CeliumCompute.ai](https://celiumcompute.ai). 

1.  Sign up or log in to your CeliumCompute account.
2.  Navigate to your API key settings (usually in your account or profile section).
3.  Generate or copy your API key.

### 3. Configure Lium CLI

Set your API key (this is required):
```bash
lium config set api_key YOUR_API_KEY_HERE
```

Set the path to your **public** SSH key. This key will be automatically added to new pods you create, allowing you to SSH in.
```bash
lium config set ssh.key_path ~/.ssh/your_public_key.pub
```
(Replace `~/.ssh/your_public_key.pub` with the actual path to your public SSH key.)

To see your current configuration:
```bash
lium config show
```

To see where the config file is stored:
```bash
lium config path
```

## 🚀 Usage Examples

**1. List available GPU executor types:**

```bash
lium ls
```
This will show a summary table. Enter a GPU type (e.g., `H100`) to see detailed specs for available executors of that type, sorted by Pareto optimality (best bang for your buck across multiple specs!).

**2. Launch a new pod:**

```bash
# Launch a pod on an executor (identified by its HUID from 'lium ls')
# This will prompt you to select a template if --template-id is not given
lium up swift-hawk-a7 my-first-pod

# Launch using a specific template and the default first template with -y (yes to all prompts)
lium up brave-lion-3c my-fast-pod --template-id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
lium up clever-fox-b2 --yes # Uses default name (HUID) and first template

# Launch multiple pods with a name prefix, using the default template automatically
lium up cosmic-eagle-1a,digital-viper-2b my-batch-pods --yes 
```

**3. List your active pods:**

```bash
lium ps
```
Output includes a human-readable "Name" (HUID), the label you gave it, status, GPU config, cost, uptime, and SSH command.

**4. SSH into a pod:**

Copy the SSH command from `lium ps` output and paste it into your terminal.

**5. Terminate pods:**

```bash
# Terminate a single pod by its Name (HUID from 'lium ps')
lium down swift-hawk-a7

# Terminate multiple pods (space or comma-separated Names/HUIDs)
lium down brave-lion-3c clever-fox-b2,cosmic-eagle-1a

# Terminate all your active pods (will ask for confirmation)
lium down --all

# Terminate all without confirmation
lium down --all -y
```

**6. Change CLI theme:**

```bash
lium theme solarized-light
lium theme mono # Back to default dark monochrome
```

## 🛠️ Configuration Keys

*   `api_key` (string, required): Your CeliumCompute.ai API key.
*   `ssh.key_path` (string, required): Absolute path to your *public* SSH key file (e.g., `~/.ssh/id_ed25519.pub`). One key per line if the file contains multiple.
*   `user.default_region` (string, optional): Future use for setting a default deployment region.

Use `lium config set <key> <value>` to manage these. For nested keys, use dot notation (e.g., `lium config set ssh.key_path ~/.ssh/another_key.pub`).

## 🤝 Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## 📜 License

[Specify Your License Here - e.g., MIT License]

---

Happy Computing with Lium! 🎉
