# xStocks Bot

Multi-account automation for xStocks account registration and daily spin reveal.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Account data is stored in `data/accounts.json`, which is intentionally gitignored.

## Usage

Generate or import accounts:

```bash
python generate_wallets.py
```

Assign proxies:

```bash
python generate_wallets.py --proxies data/new_proxies.txt
```

Run registration and daily tasks:

```bash
python run_batched.py
```

Run daily mode for already registered accounts:

```bash
python run_batched.py gm
```

Reveal daily spin only:

```bash
python reveal_only.py
```

## Security

- Do not commit `data/accounts.json`, `.env`, proxy lists, logs, state files, or virtualenvs.
- Private keys and proxy credentials must stay in gitignored local files only.
