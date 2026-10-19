# Stage 4b: manual experiments (install notes)

Run these in the Loopforge project folder, in the terminal with `(.venv)` active.

1. Unzip this folder's contents into the project root, merging folders. New files:
   `src/loopforge/manual.py`, `src/loopforge/safety.py`, `tests/test_manual.py`, `docs/EXPERIMENTS.md`, `apply_patch.py`.
   (If your docs are not in a `docs/` folder, put `EXPERIMENTS.md` wherever your other docs are.)
2. Patch the existing files (small exact edits; it stops and changes nothing if a file looks different):

   ```
   python apply_patch.py
   ```
3. Check everything:

   ```
   pytest
   loopforge exp --help
   ```
   Expect all earlier tests plus the new `test_manual.py` to pass.
4. Commit: `git add -A` then `git commit -m "Stage 4b: manual experiment workflow"`.

Then follow `docs/EXPERIMENTS.md`, starting with a throwaway dry run.
