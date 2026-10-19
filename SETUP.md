# Setup guide (beginner-friendly)

You only need to do this once.

## 1. Install Python

You need Python 3.10 or newer. Check what you have by opening a terminal
(Mac: Terminal app; Windows: PowerShell) and running:

```
python --version
```

On Mac you may need `python3 --version`. If it is missing or too old, download it from
https://www.python.org/downloads/ . On Windows, tick **"Add Python to PATH"** in the installer.

## 2. Put the project on your computer

1. Download `loopforge-stage4.zip` from the chat (or unzip `loopforge-stage4-changes.zip` over your Stage 3 folder).
2. Unzip it somewhere you will remember, for example your Documents folder.
   You should end up with a folder named `loopforge` containing `README.md`, `src`, `tests`, etc.

## 3. Open a terminal inside the folder

```
cd path/to/loopforge
```

(Tip: type `cd ` then drag the folder into the terminal window and press Enter.)

## 4. Create a virtual environment and install

A virtual environment keeps this project's packages separate from the rest of your computer.

Mac / Linux:
```
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Windows (PowerShell):
```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

When it works, your prompt starts with `(.venv)`.

## 5. Check that it works

```
pytest
loopforge baselines
loopforge doctor
```

You should see all tests pass (165 of them, about a minute), a small table where `two_opt` scores 1.000,
`nearest_neighbor` about 1.15, and `random_order` about 4.5. `loopforge doctor` shows which
sandbox protections your computer supports. On Windows some are unavailable; that is expected
and fine for now (the wall-clock timeout still works).

If `loopforge` is "not found", use `python -m loopforge.cli baselines` instead.

## 5b. Run your first search

```
loopforge search --budget 100
```

This takes a few seconds. Each of the 100 proposals is a random edit to the nearest-neighbor code,
tested in the sandbox. **Seeing `0 improvements` is normal and expected**: blind random edits
cannot improve nearest neighbor (see `docs/RESULTS.md`). That is the baseline the LLM will have to beat.

Look at what happened:

```
loopforge report runs/mutation-evolve-s0
```

and open `runs/mutation-evolve-s0/programs.jsonl` in a text editor to see every proposal, whether
it worked, and why it failed. To run the full comparison (about 3 minutes):

```
loopforge experiment --budget 300 --seeds 10 --workers 2 --out runs/exp1
```

## 5c. Optional: use an LLM (Stage 4)

See `docs/LLM.md`. Start with `loopforge llm-check --show-prompt`, which needs no key.

## 6. Try writing your own algorithm

Create a file `my_solver.py` anywhere with:

```python
def solve(points):
    return list(range(len(points)))
```

Then run `loopforge eval my_solver.py`. Try an infinite loop (`while True: pass`) too and watch the
sandbox stop it and mark it invalid instead of freezing your computer. Try to beat nearest neighbor by hand. It helps you
understand what the AI will be trying to do.

## Git and GitHub (when you are ready)

```
git init
git add .
git commit -m "Stage 4: LLM proposer"
```

We will create the GitHub repository together in the final stage, so no rush.
