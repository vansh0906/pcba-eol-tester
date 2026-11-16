# Run it on a Mac

Copy each block as is, one at a time.

## 1. Unzip and install (Python 3.10 or newer)

```
cd ~/Downloads
```
```
unzip -q project42-pcba-eol-tester.zip
```
```
cd pcba-eol-tester
```
```
python3 -m venv .venv
```
```
source .venv/bin/activate
```
```
python3 -m pip install -r requirements.txt
```

## 2. Tests and every study

```
python3 -m pytest -q
```
Expect `10 passed`, or `9 passed, 1 skipped` until Rust is installed in step 4.
```
python3 run_all.py
```
Expect the summary lines (DFT 78.0% → 94.0%, 22.83% → 0.0% false fails, pilot FPY 96.4%, diagnosis 93.1% → 100%).
```
open docs/img/results.png
```
```
open results/report.md
```

## 3. Look at the tester log

```
head -20 results/pilot_log.csv
```

## 4. Rust log analytics

Install Rust once (official installer, about 2 minutes):
```
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
```
```
source "$HOME/.cargo/env"
```
```
cd tools/tlog
```
```
cargo test
```
```
cargo run --release -- ../../results/pilot_log.csv
```
```
cd ../..
```

## 5. Push to GitHub

Create the empty repository `pcba-eol-tester` on github.com (no README, no license), then:
```
git remote add origin https://github.com/vansh0906/pcba-eol-tester.git
```
```
git push -u origin main
```
Open the Actions tab: `python` and `rust` should both be green.
