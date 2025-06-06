#!/usr/bin/env python3
"""
Example usage of the Lium SDK

This script demonstrates how to use the integrated Lium SDK
for programmatic pod management.
"""

from lium import Lium, PodInfo, ExecutorInfo
import time


def main():
    """Demonstrate Lium SDK usage."""
    
    # Initialize SDK - uses same config as CLI
    try:
        lium = Lium()
        print("✅ Lium SDK initialized successfully")
    except ValueError as e:
        print(f"❌ Failed to initialize SDK: {e}")
        print("Make sure to run 'lium init' first or set LIUM_API_KEY environment variable")
        return
    
    # List available executors
    print("\n📋 Listing available executors...")
    try:
        executors = lium.list_executors()
        print(f"Found {len(executors)} total executors")
        
        # Group by GPU type
        gpu_types = {}
        for executor in executors:
            if executor.gpu_type not in gpu_types:
                gpu_types[executor.gpu_type] = []
            gpu_types[executor.gpu_type].append(executor)
        
        print("\nAvailable GPU types:")
        for gpu_type, execs in gpu_types.items():
            prices = [e.price_per_gpu_hour for e in execs]
            min_price = min(prices)
            max_price = max(prices)
            print(f"  {gpu_type}: {len(execs)} executors, ${min_price:.2f}-${max_price:.2f}/GPU/hour")
        
    except Exception as e:
        print(f"❌ Failed to list executors: {e}")
        return
    
    # Show current pods
    print("\n🖥️  Listing current pods...")
    try:
        pods = lium.list_pods()
        if pods:
            print(f"Found {len(pods)} active pods:")
            for pod in pods:
                print(f"  - {pod.name} ({pod.huid}): {pod.status}")
        else:
            print("No active pods found")
    except Exception as e:
        print(f"❌ Failed to list pods: {e}")
    
    # Show available templates
    print("\n📦 Available templates:")
    try:
        templates = lium.get_templates()
        for i, template in enumerate(templates[:3]):  # Show first 3
            print(f"  {i+1}. {template['name']}: {template['docker_image']}:{template.get('docker_image_tag', 'latest')}")
        if len(templates) > 3:
            print(f"  ... and {len(templates)-3} more")
    except Exception as e:
        print(f"❌ Failed to get templates: {e}")
    
    # Interactive demo
    print("\n" + "="*50)
    print("🚀 INTERACTIVE DEMO")
    print("="*50)
    
    
    # Find a cheap executor for demo
    print("\n🔍 Finding a suitable executor for demo...")
    try:
        # Try to find RTX 4090 or similar for demo (usually cheaper than H100)
        demo_executors = []
        for gpu_type in ["4090", "3090", "A100", "H100"]:
            gpu_executors = lium.list_executors(gpu_type=gpu_type)
            if gpu_executors:
                demo_executors = gpu_executors
                break
        
        if not demo_executors:
            demo_executors = executors[:5]  # Just take first 5 if no preferred found
        
        # Sort by price and pick cheapest
        cheapest = min(demo_executors, key=lambda x: x.price_per_gpu_hour)
        print(f"Selected executor: {cheapest.huid} ({cheapest.gpu_type}) at ${cheapest.price_per_gpu_hour:.2f}/GPU/hour")
        
        # Confirm with user
        estimated_cost = cheapest.price_per_gpu_hour * 0.1  # Estimate 6 minutes
        
    except Exception as e:
        print(f"❌ Failed to find suitable executor: {e}")
        return
    
    # Start the demo pod
    print("\n🚀 Starting demo pod...")
    pod_id = None
    try:
        pod_result = lium.start_pod(
            executor_id=cheapest.id,
            pod_name=f"sdk-demo-{int(time.time())}"
        )
        pod_id = pod_result['id']
        print(f"✅ Pod started: {pod_id}")
        
        # Wait for pod to be ready
        print("⏳ Waiting for pod to be ready (this may take 2-3 minutes)...")
        if not lium.wait_for_pod_ready(pod_id, max_wait=300):
            print("❌ Pod failed to start within 5 minutes")
            return
        
        print("✅ Pod is ready!")
        
        # Execute some demo commands
        print("\n💻 Running demo commands...")
        
        commands = [
            ("System info", "uname -a"),
            ("GPU info", "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader"),
            ("Python version", "python3 --version"),
            ("Disk space", "df -h /"),
        ]
        
        for desc, cmd in commands:
            print(f"\n🔧 {desc}...")
            try:
                result = lium.execute_command(pod_id=pod_id, command=cmd, timeout=15)
                if result['success']:
                    output = result['stdout'].strip()
                    if output:
                        print(f"   {output}")
                    else:
                        print("   (no output)")
                else:
                    print(f"   ❌ Failed: {result['stderr']}")
            except Exception as e:
                print(f"   ❌ Error: {e}")
        
        print("\n🎉 Demo completed successfully!")
        print(f"Estimated cost: ~${cheapest.price_per_gpu_hour * 0.1:.3f}")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
    
    finally:
        # Always clean up the pod
        if pod_id:
            print(f"\n🧹 Cleaning up demo pod: {pod_id}")
            try:
                lium.stop_pod(pod_id=pod_id)
                print("✅ Pod stopped successfully")
            except Exception as e:
                print(f"❌ Failed to stop pod: {e}")
                print(f"   Please manually stop pod {pod_id} to avoid charges")
    
    print("\n✨ Lium SDK demo complete!")
    print("The SDK provides full programmatic access to all CLI functionality.")


if __name__ == "__main__":
    main() 