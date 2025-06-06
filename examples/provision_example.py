#!/usr/bin/env python3
"""
Example: GPU Machine Learning with Jupyter Notebook

This example demonstrates a typical ML workflow:
1. Start a GPU instance
2. Upload a sample dataset
3. Install Python and Jupyter
4. Launch Jupyter notebook
5. Port forward to access notebook locally
"""

from pathlib import Path

from lium import LiumPodClient


def main():
    print("🚀 Starting GPU ML Instance with Jupyter")
    print("=" * 50)

    # Initialize client
    client = LiumPodClient()

    # Get asset file paths
    assets_dir = Path(__file__).parent / "assets"
    dataset_path = assets_dir / "sample_dataset.csv"
    notebook_path = assets_dir / "demo_notebook.ipynb"

    # Step 1: Start GPU instance
    print("\n1. Starting GPU instance...")
    instance = client.start_instance(instance_name="ml-notebook")
    print(f"✓ GPU instance ready: {instance.name} ({instance.id})")

    with instance.ssh() as ssh:
        # Step 2: Upload sample dataset and notebook
        print("\n2. Uploading ML assets...")
        ssh.run("mkdir -p /root/ml_workspace").raise_on_error()
        ssh.upload(str(dataset_path), "/root/ml_workspace/dataset.csv")
        ssh.upload(str(notebook_path), "/root/ml_workspace/demo.ipynb")
        print("✓ Dataset and notebook uploaded to /root/ml_workspace/")

        # Step 3: Install Python environment and dependencies
        print("\n3. Setting up Python environment...")
        ssh.run("apt-get update -qq").raise_on_error()
        ssh.run("apt-get install -y python3 python3-pip python3-venv tmux").raise_on_error()

        # Create virtual environment and install ML packages
        ssh.run("python3 -m venv /root/ml_env").raise_on_error()
        ssh.run("/root/ml_env/bin/pip install --upgrade pip").raise_on_error()
        ssh.run("/root/ml_env/bin/pip install jupyter pandas numpy scikit-learn matplotlib seaborn").raise_on_error()
        print("✓ Python environment and ML packages installed")

        # Step 4: Start Jupyter server
        print("\n4. Starting Jupyter notebook server...")
        jupyter_cmd = (
            "/root/ml_env/bin/jupyter notebook "
            "--ip=0.0.0.0 --port=8888 --no-browser "
            "--allow-root --NotebookApp.token='' "
            "--NotebookApp.password='' "
            "--notebook-dir=/root/ml_workspace"
        )

        # Start Jupyter in a tmux session
        ssh.run(f"tmux new-session -d -s jupyter '{jupyter_cmd}'").raise_on_error()

        # Wait a moment for Jupyter to start
        import time
        time.sleep(3)

        print("✓ Jupyter notebook server started")

        # Step 5: Set up port forwarding
        print("\n5. Setting up port forwarding...")
        print("🔗 Creating tunnel: localhost:8888 -> remote:8888")

        with ssh.port_forward(local_port=8888, remote_port=8888) as tunnel:
            if tunnel.is_active:
                print("✅ Port forwarding active!")
                print("\n" + "=" * 60)
                print("🎉 JUPYTER NOTEBOOK IS READY!")
                print("=" * 60)
                print("📝 Open your browser and go to:")
                print("   http://localhost:8888")
                print("\n📁 Available files:")
                print("   - demo.ipynb (ML demonstration notebook)")
                print("   - dataset.csv (sample dataset)")
                print("\n💡 The notebook includes:")
                print("   • Data loading and exploration")
                print("   • Model training with scikit-learn")
                print("   • Performance evaluation")
                print("   • Feature importance visualization")
                print("\n⏹️  To stop: Press Ctrl+C or close this terminal")
                print("=" * 60)

                try:
                    # Keep the tunnel open until user interrupts
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\n🛑 Stopping port forward...")
            else:
                print("❌ Failed to establish port forwarding")

    print(f"\n✨ Session complete! Instance {instance.name} is still running.")
    print("💡 To stop the instance: lium down " + instance.name)


if __name__ == "__main__":
    main()
