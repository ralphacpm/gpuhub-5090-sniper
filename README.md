# gpuhub-5090-sniper

Polls the [GPUHub](https://gpuhub.com) API every few seconds and automatically deploys a container the instant an RTX 5090 becomes available.

## Requirements

```bash
pip install requests
```

## Setup

```bash
cp .env.example .env
# edit .env and paste your GPUHub API token
export GPUHUB_API_KEY=your_token_here
```

## Usage

```bash
# Watch only — no deployment fired
python3 sniper.py --dry-run

# Real snipe with PyTorch 2.8 / CUDA 12.8
python3 sniper.py --image-uuid base-image-ec1e9vdbd3

# Grab 2 GPUs, faster polling, custom startup script
python3 sniper.py \
  --image-uuid base-image-ec1e9vdbd3 \
  --gpu-num 2 \
  --interval 3 \
  --cmd "bash /root/start.sh" \
  --name my-5090-run
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--interval` | `5` | Poll interval in seconds |
| `--regions` | both | `Singapore-A` and/or `Singapore-B` |
| `--gpu-num` | `1` | Number of 5090s to request |
| `--image-uuid` | required | Public or private image UUID |
| `--cmd` | `sleep infinity` | Container startup command |
| `--name` | `sniper-5090` | Deployment name |
| `--price-max` | unlimited | Max price in USD×1000 (e.g. `5000` = $5/hr cap) |
| `--cuda-min` | `118` | Min CUDA version: `118`=11.8, `120`=12.0, `128`=12.8 |
| `--list-images` | — | Print your private images and exit |
| `--dry-run` | — | Poll without deploying |

## Public base images

| UUID | Image |
|------|-------|
| `base-image-ec1e9vdbd3` | PyTorch 2.8.0 / CUDA 12.8 |
| `base-image-lbdbb183fk` | PyTorch 2.1.2 / CUDA 11.8 |
| `base-image-8hkyyugih5` | Miniconda / CUDA 11.8 |

## Keep it running in the background

```bash
tmux new -s sniper
python3 sniper.py --image-uuid base-image-ec1e9vdbd3
# Ctrl+B then D to detach
# tmux attach -t sniper to come back
```
