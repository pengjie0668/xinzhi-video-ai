# Xinzhi Video AI Deployment

This project is intended to run from:

```bash
/home/dev_jie/xinzhi-video-ai
```

## Basic Setup

```bash
git clone https://github.com/pengjie0668/xinzhi-video-ai.git /home/dev_jie/xinzhi-video-ai
cd /home/dev_jie/xinzhi-video-ai
uv sync
uv run playwright install chromium
```

Install system dependencies when needed:

```bash
sudo apt update
sudo apt install -y ffmpeg fonts-noto-cjk
sudo uv run playwright install-deps chromium
```

## Configuration

Copy the example config and fill API keys on the server:

```bash
cp config.example.yaml config.yaml
```

Do not commit `config.yaml`; it is intentionally ignored because it may contain API keys.

## systemd Service

```bash
sudo cp deploy/systemd/xinzhi-video-ai.service /etc/systemd/system/xinzhi-video-ai.service
sudo systemctl daemon-reload
sudo systemctl enable xinzhi-video-ai.service
sudo systemctl start xinzhi-video-ai.service
```

Check status:

```bash
systemctl status xinzhi-video-ai.service --no-pager
curl -I http://127.0.0.1:8501
```
