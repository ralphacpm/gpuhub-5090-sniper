#!/usr/bin/env python3
"""
GPUHub RTX 5090 Sniper
Polls GPU stock across all regions and auto-deploys the moment a 5090 becomes available.

Usage:
    python3 sniper.py --list-images          # see available images
    python3 sniper.py --dry-run              # poll only, no deployment
    python3 sniper.py --image-uuid base-image-ec1e9vdbd3

Public base image UUIDs (PyTorch + CUDA 12.8):
    base-image-ec1e9vdbd3   PyTorch 2.8.0 / CUDA 12.8
    base-image-lbdbb183fk   PyTorch 2.1.2 / CUDA 11.8
    base-image-8hkyyugih5   Miniconda / CUDA 11.8
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional; fall back to shell env

API_BASE = "https://api.gpuhub.com"
API_KEY = os.environ.get("GPUHUB_API_KEY", "")

if not API_KEY:
    print("Error: GPUHUB_API_KEY is not set.")
    print("  Option 1: export GPUHUB_API_KEY=your_token_here")
    print("  Option 2: put GPUHUB_API_KEY=your_token_here in a .env file")
    sys.exit(1)

HEADERS = {
    "Authorization": API_KEY,
    "Content-Type": "application/json",
}

TARGET_GPU = "RTX 5090"

# Both regions that hold 5090s
ALL_REGIONS = ["Singapore-A", "Singapore-B"]


def ts():
    return datetime.now().strftime("%H:%M:%S")


def check_stock(region: str) -> int:
    """Returns idle 5090 count in the given region."""
    r = requests.post(
        f"{API_BASE}/api/v1/dev/machine/region/gpu_stock",
        headers=HEADERS,
        json={"region_sign": region, "gpu_name_set": [TARGET_GPU]},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Success":
        raise RuntimeError(f"Stock check error: {data}")
    for entry in data.get("data", []):
        info = entry.get(TARGET_GPU, {})
        return int(info.get("idle_gpu_num", 0))
    return 0


def poll_all_regions(regions: list[str]) -> dict[str, int]:
    """Checks all regions in parallel and returns {region: idle_count}."""
    result = {}
    with ThreadPoolExecutor(max_workers=len(regions)) as executor:
        futures = {executor.submit(check_stock, region): region for region in regions}
        for future in as_completed(futures):
            region = futures[future]
            try:
                result[region] = future.result()
            except Exception as e:
                result[region] = -1
                print(f"\n[{ts()}] Warning: failed to check {region}: {e}")
    return result


def create_deployment(
    regions: list[str],
    gpu_num: int,
    image_uuid: str,
    name: str,
    cmd: str,
    price_max: int,
    cuda_min: int,
) -> str:
    """Fires a deployment and returns its UUID."""
    payload = {
        "name": name,
        "deployment_type": "Container",
        "reuse_container": False,
        "container_template": {
            "gpu_name_set": [TARGET_GPU],
            "gpu_num": gpu_num,
            "cpu_num_from": 2,
            "cpu_num_to": 128,
            "memory_size_from": 8,
            "memory_size_to": 512,
            "cuda_v_from": cuda_min,
            "cuda_v_to": 999,
            "dc_list": regions,
            "price_from": 0,
            "price_to": price_max,
            "image_uuid": image_uuid,
            "cmd": cmd,
        },
    }
    r = requests.post(
        f"{API_BASE}/api/v1/dev/deployment",
        headers=HEADERS,
        json=payload,
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Success":
        raise RuntimeError(f"Deployment failed: {data}")
    return data["data"]["deployment_uuid"]


def list_images() -> list[dict]:
    r = requests.post(
        f"{API_BASE}/api/v1/dev/image/private/list",
        headers=HEADERS,
        json={"page_index": 0, "page_size": 50},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("data", {}).get("list", [])


def main():
    parser = argparse.ArgumentParser(
        description="GPUHub RTX 5090 sniper — grabs a 5090 the instant one goes idle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--interval", type=float, default=5.0,
                        help="Poll interval in seconds (default: 5)")
    parser.add_argument("--regions", nargs="+", default=ALL_REGIONS,
                        help=f"Regions to watch (default: {ALL_REGIONS})")
    parser.add_argument("--gpu-num", type=int, default=1,
                        help="Number of 5090s to request (default: 1)")
    parser.add_argument("--image-uuid", default="",
                        help="Image UUID to deploy (see --list-images or the docstring above)")
    parser.add_argument("--cmd", default="sleep infinity",
                        help="Container startup command (default: sleep infinity)")
    parser.add_argument("--name", default="sniper-5090",
                        help="Deployment name (default: sniper-5090)")
    parser.add_argument("--price-max", type=int, default=99999,
                        help="Max price in USD*1000, e.g. 5000 = $5/hr (default: no limit)")
    parser.add_argument("--cuda-min", type=int, default=118,
                        help="Min CUDA version code: 118=11.8, 120=12.0, 128=12.8 (default: 118)")
    parser.add_argument("--list-images", action="store_true",
                        help="Print your private images and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Poll only — do not deploy when GPU is found")
    args = parser.parse_args()

    if args.list_images:
        images = list_images()
        if not images:
            print("No private images found. Use a public image UUID (see script header).")
        else:
            for img in images:
                print(f"  {img['image_uuid']}  {img['image_name']}")
        return

    if not args.image_uuid and not args.dry_run:
        parser.error("--image-uuid is required (run --list-images or pick one from the script header)")

    print(f"[{ts()}] GPUHub RTX 5090 Sniper")
    print(f"  Target  : {TARGET_GPU} x{args.gpu_num}")
    print(f"  Regions : {args.regions}")
    print(f"  Interval: {args.interval}s")
    print(f"  Image   : {args.image_uuid or '(dry-run, no image)'}")
    print(f"  Dry run : {args.dry_run}")
    print()

    consecutive_errors = 0

    while True:
        try:
            stock = poll_all_regions(args.regions)
            available = {r: n for r, n in stock.items() if n >= args.gpu_num}
            consecutive_errors = 0

            if available:
                best_region = max(available, key=lambda r: available[r])
                idle_count = available[best_region]
                print(f"\n[{ts()}] *** FOUND {idle_count}x {TARGET_GPU} in {best_region}! ***", flush=True)

                if args.dry_run:
                    print(f"[{ts()}] Dry-run — skipping deployment. Continuing to poll.")
                else:
                    print(f"[{ts()}] Firing deployment '{args.name}' ...")
                    uuid = create_deployment(
                        regions=[best_region],
                        gpu_num=args.gpu_num,
                        image_uuid=args.image_uuid,
                        name=args.name,
                        cmd=args.cmd,
                        price_max=args.price_max,
                        cuda_min=args.cuda_min,
                    )
                    print(f"[{ts()}] Deployment created: {uuid}")
                    print(f"")
                    print(f"  *** ACTION REQUIRED ***")
                    print(f"  RTX 5090 requires a Duration Package — go to the dashboard NOW:")
                    print(f"  https://www.gpuhub.com/deploy/elastic/{uuid}")
                    print(f"  Click 'Purchase Duration Package' before the container is killed.")
                    print(f"")
                    print(f"[{ts()}] Waiting 5 minutes for you to purchase the package (Ctrl+C to exit early)...")
                    try:
                        for remaining in range(300, 0, -1):
                            print(f"  {remaining}s remaining...    ", end="\r", flush=True)
                            time.sleep(1)
                    except KeyboardInterrupt:
                        pass
                    print(f"\n[{ts()}] Done.")
                    return
            else:
                status_parts = []
                for region in args.regions:
                    n = stock.get(region, -1)
                    status_parts.append(f"{region}:{n if n >= 0 else 'err'}")
                print(f"[{ts()}] Watching... {' | '.join(status_parts)}", end="\r", flush=True)

        except requests.HTTPError as e:
            consecutive_errors += 1
            print(f"\n[{ts()}] HTTP error ({consecutive_errors}): {e}")
        except KeyboardInterrupt:
            print(f"\n[{ts()}] Stopped by user.")
            return
        except Exception as e:
            consecutive_errors += 1
            print(f"\n[{ts()}] Error ({consecutive_errors}): {e}")

        if consecutive_errors >= 10:
            print(f"[{ts()}] 10 consecutive errors — giving up.")
            sys.exit(1)

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
