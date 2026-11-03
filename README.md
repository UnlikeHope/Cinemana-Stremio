# Cinemana Stremio Add-on

A minimal Stremio stream add-on that finds movies and series episodes on Shabakaty's Cinemana by IMDb ID and returns direct stream URLs, with subtitles when available.

## Requirements

- Python 3.9+
- Dependencies listed in `requirements.txt`

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python addon.py
```

The add-on listens on `http://127.0.0.1:5069` by default. To use a different port:

```bash
PORT=8080 python addon.py
```

With Nix:

```bash
nix run
```

Or enter a development shell:

```bash
nix develop
python addon.py
```

With Docker:

```bash
docker build -t cinemana-stremio .
docker run --rm -p 5069:5069 cinemana-stremio
```

## Install in Stremio

1. Start the add-on.
2. Open Stremio Desktop.
3. Go to **Addons → Install from URL**.
4. Enter:

```text
http://127.0.0.1:5069/manifest.json
```

Stremio must run on the same machine as the add-on. Stremio Web may not allow localhost add-ons; use the desktop app.
