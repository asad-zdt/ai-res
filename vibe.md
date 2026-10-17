
Vibe Coding Guide: AI Resource Allocation Engine
Oct 17, 2026 · @Asad
Build the whole engine solo in 8 phases: for each phase you paste one detailed prompt into your AI coding tool, run a short check yourself, then commit.
How to vibe-code this project
Use an agentic coding tool that can read your repo and run commands: Claude Code in a WSL2 or Linux terminal is the best fit, with Cursor or Windsurf as alternatives. Run everything inside Linux, because cgroups v2 in Phase 4 does not exist on Windows or macOS.
The loop for every task:
1. Start a fresh AI session per phase and paste the master context prompt (next section), then that phase's prompt.
2. Ask for a plan first: "plan only, no code". Fix the plan before it writes anything.
3. Let it build one task at a time, matching the M1-T1, M2-T1 style task IDs from your plan.
4. Run the check yourself. Do not trust "it works" from the AI.
5. Paste errors back verbatim, with the command you ran.
6. Commit to git when the check is green, then move on.
Every prompt has four parts: context (what exists already), task (exact files to create), constraints (what it must not touch), and verification (the command that proves it works). The prompts below all follow this shape, so edit the details, not the structure.
Rules that save you days:
• One task per prompt. Prompts that say "build the whole backend" produce code you cannot debug.
• Freeze docs/api_contract.md and service/schemas.py after Phase 0. Tell the AI never to edit them unless you ask.
• Make it write a smoke test or a __main__ demo with each module, so every file is runnable on its own.
• Commit after every green check. Git is your undo button when the AI breaks something.
• Save the master context prompt as CLAUDE.md (Claude Code) or .cursorrules (Cursor) in the repo root, so you stop re-pasting it.
Master context prompt
Paste this at the start of every session, or save it as CLAUDE.md in the repo root. Add one line at the bottom each time saying which phase and task you are on.
You are my pair-programmer on a solo project: an AI Resource Allocation Engine.

GOAL
Predict an application's resource needs (CPU %, RAM MB, disk MB/s, network KB/s)
BEFORE it runs, using its name and its historical behaviour. Then use the
prediction for OS-level admission control and resource caps on Linux
(cgroups v2 + process niceness).

STACK
Python 3.11+, psutil, pandas, scikit-learn, joblib, FastAPI + uvicorn,
Pydantic v2, PyYAML, pytest. Dashboard: Streamlit. Linux only
(WSL2 with systemd enabled, or a Linux VM).

REPO LAYOUT
collector/  features/  model/  service/  os_integration/  gui/
data/raw/  data/sample/  data/processed/  docs/  reports/  tests/

FROZEN CONTRACTS (never edit unless I explicitly say so)
- docs/api_contract.md and service/schemas.py. Read the contract before
  doing any work (it exists after Phase 0).
- Feature columns, in this order: app_name, app_category, exe_size_mb,
  hist_avg_cpu_pct, hist_avg_ram_mb, hist_avg_disk_mbps, hist_avg_net_kbps
- Target columns, in this order: cpu_pct, ram_mb, disk_mbps, net_kbps
- Endpoints: POST /predict and POST /run-and-compare, both taking
  {"app_name": "chrome"}.

WORKING RULES
1. Build only the task I name in this message. Do not start other tasks
   and do not refactor unrelated files.
2. Before writing code, give a short plan: files, functions, how you will
   test it. Wait for me to say "go".
3. Every module must run on its own (an `if __name__ == "__main__"` demo)
   or ship with a pytest test.
4. Type hints and docstrings on public functions. Small functions, no
   global state.
5. Resolve paths from the repo root through one helper in config.py.
   Never hardcode absolute paths.
6. When finished, tell me: files changed, the exact commands to verify,
   and the output I should see. Then stop.
7. If a requirement is ambiguous, ask me one question instead of guessing.

CURRENT PHASE / TASK: <fill this in each session>
Phase 0: Foundation (about 0.5 day)
Goal: freeze the contracts so nothing shifts under you later. Three prompts, three commits.
Prompt 0.1: repo skeleton and API contract
TASK: Create the repo skeleton and the API contract. Plan first, then wait for "go".

1. Create these folders, each with an empty __init__.py where it is a Python
   package: collector/, features/, model/, model/artifacts/, service/,
   os_integration/, gui/, data/raw/, data/sample/, data/processed/, docs/,
   reports/, tests/. Add .gitkeep to empty data folders.
2. Create requirements.txt with pinned-minimum versions: psutil, pandas,
   numpy, scikit-learn, joblib, fastapi, uvicorn[standard], pydantic>=2,
   pyyaml, httpx, requests, streamlit, plotly, pytest.
3. Create .gitignore (venv, __pycache__, .pytest_cache, data/raw/*.csv,
   model/artifacts/*.pkl, .env).
4. Create config.py at the repo root with: REPO_ROOT (resolved from the
   file location), path constants for every data/model/report folder,
   FEATURE_COLUMNS and TARGET_COLUMNS lists in the exact order from my
   context prompt, and API_HOST/API_PORT (127.0.0.1 / 8000).
5. Create docs/api_contract.md containing:
   a) Feature schema and target schema as tables: column, type, unit,
      meaning.
   b) Metric definitions, written down once so every module agrees:
      cpu_pct = mean of summed CPU% over the whole process tree during the
      run (can exceed 100 on multi-core); ram_mb = PEAK resident set size
      summed over the process tree; disk_mbps = mean (read+write) MB/s of
      the process tree; net_kbps = mean system-wide network KB/s during the
      run (psutil has no per-process network counters, so note this as a
      known limitation).
   c) POST /predict. Request: {"app_name": "chrome"}. Response:
      {"app_name": "chrome", "predicted": {"cpu_pct": 35.2, "ram_mb": 820.5,
      "disk_mbps": 1.4, "net_kbps": 210.0}, "source": "model" | "mock"}.
   d) POST /run-and-compare. Same request. Response: app_name, predicted
      (as above), actual (same four keys), duration_s (float), and
      enforcement: {admitted: bool, reason: string|null, niceness: int|null,
      cgroup_applied: bool}.
   e) Errors: 404 {"detail": "Unknown app: <name>"} for apps not in
      collector/apps_config.yaml, 422 for validation errors, 409 when
      admission control refuses the launch.
6. Add a short README.md stub: project name, one-paragraph goal, "setup
   coming later".

Do NOT write any other code. Verification: run `python -c "import config;
print(config.FEATURE_COLUMNS, config.TARGET_COLUMNS)"` and show me the
output.
Check: the command prints both column lists, and docs/api_contract.md reads sensibly to you. Then git init, commit "phase 0.1: skeleton and contract".
Prompt 0.2: sample dataset
TASK: Create a reproducible sample dataset so the model, API and GUI can be
built before any real data exists.

Write data/sample/make_sample.py (numpy seed 42) that generates
data/sample/sample_dataset.csv with 40 rows: 8 apps x 5 runs each.
Apps and categories: chrome (browser), firefox (browser), vscode (editor),
gedit (editor), ffmpeg (media), python_script (script), gcc_build
(compiler), vlc (media).

Columns, exact order: app_name, app_category, exe_size_mb, hist_avg_cpu_pct,
hist_avg_ram_mb, hist_avg_disk_mbps, hist_avg_net_kbps, then the targets
cpu_pct, ram_mb, disk_mbps, net_kbps.

Realism rules:
- Give each app a fixed base profile (for example chrome: ~45% CPU,
  ~900 MB RAM, low disk, medium network; ffmpeg: ~180% CPU, ~400 MB RAM,
  high disk, ~0 network; gedit: ~3% CPU, ~120 MB RAM; gcc_build: ~250% CPU,
  ~1500 MB RAM, medium disk). Add 10-20% gaussian noise per run to targets.
- exe_size_mb and app_category are constant per app.
- hist_avg_* for run k = mean of the same app's targets over runs 1..k-1;
  for run 1 use the app's base profile with small noise. No NaNs anywhere.
- All values non-negative, rounded to 2 decimals.

Run the script and commit both the script and the CSV. Verification: print
df.groupby('app_name').mean(numeric_only=True) and df.isna().sum().sum().
Check: 40 rows, zero NaNs, and app means that look believable. Commit.
Prompt 0.3: schemas as code
TASK: Write service/schemas.py (Pydantic v2) that implements
docs/api_contract.md exactly. Do not change the contract; if you find a
contradiction, stop and ask me.

Models:
- ResourceMetrics: cpu_pct, ram_mb, disk_mbps, net_kbps (float, >= 0).
- PredictRequest: app_name (str). Validator: strip whitespace, lower-case,
  must match ^[a-z0-9_.-]{1,64}$ (this blocks path tricks and shell
  injection), else raise a validation error.
- PredictResponse: app_name, predicted: ResourceMetrics, source: Literal
  ["model", "mock"].
- EnforcementInfo: admitted (bool), reason (str | None), niceness
  (int | None), cgroup_applied (bool).
- RunAndCompareResponse: app_name, predicted, actual (ResourceMetrics),
  duration_s (float >= 0), enforcement (EnforcementInfo).

Also write tests/test_schemas.py with pytest cases: valid request, upper
case gets normalised, empty string rejected, "../etc/passwd" rejected,
negative metric rejected, a full RunAndCompareResponse round-trips through
model_dump / model_validate.

Verification: `pytest tests/test_schemas.py -q` should be all green.
Exit: pytest is green, contract plus sample CSV plus schemas are committed, and you will not edit them casually from here on.
Phase 1: Vertical slice on sample data (about 1 day)
Goal: POST /predict works end to end with a real trained model, using only the sample CSV. From here on you always have a working demo.
Prompt 1.1: mock predictor and FastAPI skeleton
TASK (M3-T2 + first half of M3-T3): mock predictor and the /predict API.
Plan first, then wait for "go".

1. errors.py at repo root: class UnknownAppError(KeyError) with the app name
   in the message.
2. service/mock_predict.py: mock_predict(app_name: str) -> dict with the
   four target keys. Use a hardcoded profile dict for the 8 sample apps
   (same base values as data/sample/make_sample.py). Deterministic: same
   input, same output (no randomness). Unknown app -> UnknownAppError.
3. service/app.py: FastAPI app.
   - POST /predict takes PredictRequest, returns PredictResponse (both from
     service/schemas.py, unchanged).
   - Choose the predictor from env var PREDICTOR ("mock" or "model").
     For now "model" is not built, so default to "mock" and set
     source="mock" in the response.
   - UnknownAppError -> HTTP 404 {"detail": "Unknown app: <name>"}.
   - Also add GET /health returning {"status": "ok", "predictor": <name>}
     (a utility endpoint outside the contract).
   - Enable CORS for http://localhost:8501 (Streamlit) so a browser GUI
     can call it later.
4. tests/test_api.py using fastapi.testclient: valid app returns 200 with
   all four keys, unknown app returns 404, invalid name returns 422.

Constraints: do not edit docs/ or service/schemas.py. Verification:
`pytest tests/test_api.py -q`, then
`uvicorn service.app:app --port 8000` and
`curl -s -X POST localhost:8000/predict -H 'Content-Type: application/json'
-d '{"app_name":"chrome"}'`. Show me the curl output.
Check: run the curl yourself and compare against the contract. Commit.
Prompt 1.2: training script
TASK (M2-T1): model/train.py, a multi-output regression training script.
Plan first, then wait for "go".

CLI: `python -m model.train --data data/sample/sample_dataset.csv
--out model/artifacts/model.pkl` (both args optional, those are the
defaults; later phases will point --data at data/processed/dataset.csv).

Requirements:
- Load the CSV, validate that it has every column in config.FEATURE_COLUMNS
  + config.TARGET_COLUMNS and no NaNs; fail with a clear message if not.
- Model: a scikit-learn Pipeline = ColumnTransformer (one-hot encode
  app_category with handle_unknown="ignore"; pass numeric features through;
  DROP app_name because it is only the lookup key, not a predictive
  feature) followed by RandomForestRegressor(n_estimators=300,
  random_state=42). RandomForest supports multi-output natively.
- Split by rows 80/20 with random_state=42, fit on train, print MAE per
  target on the test split (a quick sanity print; the full evaluation
  module comes later).
- Then refit on ALL rows and save a single joblib bundle to --out:
  {"pipeline": fitted_pipeline, "feature_columns": [...],
  "target_columns": [...], "app_profiles": {app_name: {app_category,
  exe_size_mb, hist_avg_cpu_pct, hist_avg_ram_mb, hist_avg_disk_mbps,
  hist_avg_net_kbps}}, "trained_at": iso_timestamp, "n_rows": int}.
  app_profiles holds the LATEST feature row per app, because predicting
  by name needs a feature vector to look up.
- Create the output folder if missing. Add tests/test_train.py that trains
  on the sample CSV into a tmp_path and asserts the bundle has all keys.

Verification: run the CLI and show the printed MAE table; run
`pytest tests/test_train.py -q`.
Check: model/artifacts/model.pkl exists and the MAE numbers are finite. Commit (the pkl is gitignored, which is fine).
Prompt 1.3: predictor wrapper and the swap
TASK (M2-T3 + finish the swap): model/predict.py and wire it into the API.

1. model/predict.py: predict(app_name: str) -> dict[str, float] with the
   four target keys.
   - Lazy-load the bundle once (functools.lru_cache), path from env var
     MODEL_PATH, default model/artifacts/model.pkl.
   - Look up app_name in bundle["app_profiles"]; unknown ->
     errors.UnknownAppError. Build a one-row DataFrame with
     feature_columns, run pipeline.predict, clip negatives to 0, round to
     2 decimals.
   - Missing model file -> a clear FileNotFoundError telling me to run
     `python -m model.train`.
   - __main__ demo: `python -m model.predict chrome` prints the dict.
2. Update service/app.py: PREDICTOR=model uses model.predict.predict and
   returns source="model". Default = "model" if the model file exists,
   otherwise "mock". /health reports which one is active.
3. Extend tests/test_api.py to run the same checks against both
   predictors (parametrise via monkeypatch of the env var). Add
   tests/test_predict.py: known app returns four non-negative floats,
   unknown app raises UnknownAppError.

Constraints: do not touch schemas.py or the contract. Verification:
`pytest -q`, then start the server with PREDICTOR=model and curl
/predict for chrome and ffmpeg. The two answers must differ sensibly.
Exit: the curl returns "source": "model" with believable numbers for different apps. Commit "phase 1: vertical slice".
Phase 2: Data collection (about 1.5 days)
Goal: a real data/raw/runs.csv with at least 5 valid runs per app. This is the riskiest phase, so do it early and start the long benchmark run in the background before moving on.
Prompt 2.1: apps config and workloads
TASK (M1-T1): collector/apps_config.yaml plus the workload scripts it uses.
Plan first, then wait for "go".

I am on Linux/WSL2 and need 8 apps that launch non-interactively, finish in
10-60 seconds, and behave differently from each other. Mix real tools and
synthetic workloads:
  synthetic (write them in collector/workloads/, each takes CLI args, and register them in the YAML as apps named cpu_burn, mem_hog and disk_writer):
    - cpu_burn.py --seconds N --workers K  (busy loops in K processes)
    - mem_hog.py --mb N --seconds S        (allocates and touches N MB)
    - disk_writer.py --mb N                (writes then reads N MB in tmp)
  real (check each exists with `which`, tell me which are missing):
    - ffmpeg encoding a lavfi testsrc video for N seconds
    - gcc compiling a generated large C file (write a generator script)
    - sort on a generated large text file
    - curl downloading a file from a stable URL (network workload)
    - optional: chromium --headless --dump-dom https://example.com

YAML schema per app: name (lowercase, matches ^[a-z0-9_.-]{1,64}$),
category, command (a LIST of args, never a shell string), cwd,
timeout_s, variants (a list of 2-3 alternative arg sets so repeated runs
vary in size; the logger will cycle through them), and
exe (the binary used to measure exe_size_mb).

Also write collector/config_loader.py: load_apps(path=None) -> dict[name,
AppSpec dataclass], validating every field, resolving exe via
shutil.which, computing exe_size_mb, and raising a clear error for
duplicates or bad names. This loader becomes the single source of truth for
which app names the API accepts.

Verification: `python -m collector.config_loader` prints a table: name,
category, exe path, exe_size_mb, number of variants.
Check: every app resolves to a real binary. Run one command by hand to confirm it finishes in a sensible time. Commit.
Prompt 2.2: process monitor
TASK (M1-T2): collector/monitor.py, a psutil sampling loop. Plan first.

API:
  @dataclass Sample: t_s, cpu_pct, rss_mb, disk_mbps, net_kbps
  monitor_process(popen: subprocess.Popen, interval_s=1.0,
                  timeout_s=None) -> list[Sample]
  summarize(samples: list[Sample]) -> dict with the four target keys

Behaviour, in detail:
- Sample the WHOLE process tree each second: the launched process plus all
  recursive children (many apps spawn helpers). Keep a dict pid ->
  psutil.Process that persists across ticks, because psutil's
  cpu_percent(interval=None) returns 0.0 on the first call for a new Process
  object. Prime new processes when first seen and count their CPU from the
  next tick.
- cpu_pct = sum of cpu_percent over the tree (may exceed 100).
  rss_mb = sum of memory_info().rss over the tree, in MB.
- disk_mbps: per pid, use io_counters() read_bytes + write_bytes. Keep
  last-seen totals per pid so a process that exits mid-run still counts
  what it did; the sample value is the delta over the interval divided by
  elapsed time, in MB/s.
- net_kbps: psutil.net_io_counters() bytes_sent + bytes_recv delta per
  second, system-wide, in KB/s (psutil has no per-process network
  counters; document this limitation in the docstring).
- Catch psutil.NoSuchProcess, AccessDenied and ZombieProcess everywhere.
  A vanished process must never crash the loop.
- Loop ends when popen.poll() is not None (take one final sample), or when
  timeout_s is exceeded (then terminate the tree: SIGTERM, wait 3s,
  SIGKILL, and mark the run as timed out in the return value).
- Use time.monotonic() and sleep only the remaining time of each tick to
  avoid drift.
- summarize(): cpu_pct = mean, ram_mb = PEAK rss, disk_mbps = mean,
  net_kbps = mean, exactly as defined in docs/api_contract.md. Empty
  samples -> raise ValueError.

Also add tests/test_monitor.py: spawn `python -c` that allocates ~200 MB
and burns CPU for 4 seconds; assert >= 3 samples, peak RSS >= 150 MB, mean
CPU > 50. Add a __main__ demo.

Verification: `pytest tests/test_monitor.py -q` and
`python -m collector.monitor` printing the summary dict.
Check: the demo shows non-zero CPU and RAM that match what htop shows for the same process. Commit.
Prompt 2.3: run logger
TASK (M1-T3): collector/run_logger.py, automated benchmarking.
Plan first.

CLI: `python -m collector.run_logger --runs 8 [--only name1,name2]
[--cooldown 5]`.

Behaviour:
- Load apps with collector.config_loader.load_apps().
- For each app, run it until it has --runs VALID rows in data/raw/runs.csv
  (count existing rows so I can stop and resume; do not rerun finished
  apps).
- Each run: pick the next variant (cycle through variants), launch with
  subprocess.Popen(command, cwd=cwd, stdout=DEVNULL, stderr=DEVNULL,
  start_new_session=True), never shell=True. Monitor with
  collector.monitor, summarise, append one row.
- Row columns: run_id (uuid4), timestamp (ISO UTC), app_name,
  app_category, exe_size_mb, variant_index, cpu_pct, ram_mb, disk_mbps,
  net_kbps, duration_s, exit_code, n_samples, valid (bool).
- A run is valid only if exit_code == 0, n_samples >= 3, not timed out, and
  cpu_pct > 0 and ram_mb > 0. Invalid runs are still logged with
  valid=False and retried up to 2 extra times.
- Sleep --cooldown seconds between runs so the machine settles.
- Write rows with csv.DictWriter, creating the header if the file is new,
  flushing after every row so a crash loses nothing.
- Ctrl+C must stop cleanly, killing the child process tree.
- At the end, print a table: app, valid runs, mean of each metric.

Verification: `python -m collector.run_logger --runs 2 --only cpu_burn`
then show me the CSV rows.
Check: two rows appear, with plausible values and valid=True.
Step 2.4: start the real benchmark (no prompt, you run it)
mkdir -p logs
nohup python -m collector.run_logger --runs 8 > logs/collect.log 2>&1 &
tail -f logs/collect.log
Collect 8 runs per app so you still have at least 5 after filtering invalid ones. Keep the machine quiet while it runs: close the browser, pause downloads and syncing, and stay on mains power. Network numbers are system-wide, so anything else using the network pollutes them. Move on to Phase 3 coding while it runs.
Exit: at least 5 valid runs for every app, which you can confirm with python -c "import pandas as pd; d=pd.read_csv('data/raw/runs.csv'); print(d[d.valid].groupby('app_name').size())".
Phase 3: Features, real model, evaluation (about 1.5 days)
Goal: turn raw runs into model-ready features, retrain on real data, and produce honest MAE/RMSE tables. Do this while the Phase 2 benchmark finishes in the background.
Prompt 3.1: feature pipeline
TASK (M1-T4): features/feature_schema.py and features/build_dataset.py.
Plan first, then wait for "go".

features/feature_schema.py:
- Re-export FEATURE_COLUMNS and TARGET_COLUMNS from config.py (do not
  redefine them).
- validate_frame(df) -> None: raises ValueError with a readable message if
  any column is missing, any value is NaN, any numeric value is negative,
  or app_name is not a non-empty string.

features/build_dataset.py, CLI:
`python -m features.build_dataset --runs data/raw/runs.csv
--out data/processed/dataset.csv --window 5`

Logic:
1. Load runs.csv, keep only valid == True, sort by (app_name, timestamp).
2. For each app, hist_avg_<metric> for a run = mean of the PREVIOUS runs'
   <metric>, over at most the last --window runs (use shift(1) then a
   rolling mean, min_periods=1). A run must never see its own target:
   explain in a comment how your code prevents target leakage.
3. The first run of each app has no history. DROP it from the training
   dataset (do not fill with the app-wide mean, that would leak the
   future). Print how many rows were dropped.
4. Output columns exactly FEATURE_COLUMNS + TARGET_COLUMNS, order
   preserved; exe_size_mb and app_category come from the run rows.
5. Run validate_frame before writing.
6. ALSO write data/processed/app_profiles.csv: one row per app with
   app_name, app_category, exe_size_mb and hist_avg_* computed over the
   LAST --window runs INCLUDING the most recent one. This is the serving
   profile used when the API predicts a future run.
7. Print a summary: rows per app, and df.describe() of the targets.

Add tests/test_features.py using a small hand-made runs DataFrame: check
the leakage rule (hist of run 3 = mean of runs 1-2 only), the dropped first
row, and that invalid runs are excluded.

Verification: `pytest tests/test_features.py -q`, then run the CLI on the
real data/raw/runs.csv.
Check: the leakage test passes, dataset.csv has no NaNs, and every app has at least 4 rows. Commit.
Prompt 3.2: retrain on real data
TASK: update model/train.py for real data. Plan first.

1. If an app_profiles.csv sits in the same folder as --data, build the
   bundle's app_profiles from it (the serving profile). Otherwise keep the
   current fallback (latest feature row per app).
2. Replace the random 80/20 sanity split with a chronological split per
   app: the last 20% of each app's rows (at least 1) form the test set.
   Print MAE per target on it.
3. Add --model {rf,gbr,ridge} (default rf): rf = RandomForestRegressor,
   gbr = MultiOutputRegressor(GradientBoostingRegressor), ridge =
   MultiOutputRegressor(Ridge) behind a StandardScaler. Same
   preprocessing for all.
4. Keep the bundle format identical so model/predict.py and the API need
   no changes. Update tests/test_train.py if needed.

Verification: `python -m model.train --data data/processed/dataset.csv`,
then `python -m model.predict <one of my real app names>`.
Check: restart uvicorn with PREDICTOR=model, then call /predict for two of your real apps. Commit.
Prompt 3.3: evaluation module
TASK (M2-T2): model/evaluate.py. Plan first, then wait for "go".

CLI: `python -m model.evaluate --data data/processed/dataset.csv
--out reports/evaluation_metrics.md`

Compute, for each of the four targets, MAE and RMSE (sklearn.metrics), plus
MAE as a percentage of the mean target (targets are on different scales,
so raw MAE alone is not comparable).

Evaluation schemes:
A) Chronological holdout: last 2 runs of each app = test, the rest train.
B) Leave-one-app-out: for each app, train on all other apps and test on
   that app. Report per-app and averaged. This measures generalisation to
   unseen applications.

Models to compare in every scheme: the trained model type (rf, gbr, ridge,
selectable with --models), and two baselines: (1) persistence = predict the
row's own hist_avg_* values, (2) global mean of the training targets. The
baselines show whether the model actually adds value.

Output: print the tables and write them as Markdown to --out: one table per
scheme with rows = model, columns = target x (MAE, RMSE, MAE%). Also save
reports/evaluation_metrics.csv with the same numbers in long format.

Handle edge cases: an app with fewer than 3 rows is skipped with a
warning; no runtime errors on small data.

Add tests/test_evaluate.py that runs both schemes on data/sample/
sample_dataset.csv and asserts the output tables have the expected shape
and finite numbers.

Verification: `pytest tests/test_evaluate.py -q`, then run the CLI on the
real dataset and show me both tables.
Exit: model.pkl is trained on real data and reports/evaluation_metrics.md exists. If the model does not beat the persistence baseline on some target, that is a legitimate finding: keep it for the report instead of hiding it.
Phase 4: Run-and-compare and OS integration (about 1.5 days)
Goal: a launched app is admitted or refused based on its prediction, runs under CPU and memory caps, and /run-and-compare returns predicted and actual numbers side by side. This is the phase where AI-written code is most likely to look right and fail on your machine, so verify each step by hand.
Step 4.0: check your system first (you run this, no prompt)
stat -fc %T /sys/fs/cgroup            # expect: cgroup2fs
cat /sys/fs/cgroup/cgroup.controllers # expect: cpu and memory in the list
cat /proc/1/comm                      # expect: systemd
On WSL2, if PID 1 is not systemd, add [boot] then systemd=true to /etc/wsl.conf, run wsl --shutdown from Windows, and reopen. If the first line says tmpfs instead of cgroup2fs, you are on cgroups v1 and need a newer WSL kernel or a Linux VM.
Prompt 4.1: priority and cgroup enforcers
TASK (M3-T4): os_integration/priority.py, os_integration/cgroup_manager.py
and os_integration/setup_cgroup.sh. Plan first, then wait for "go".

SAFETY RULES (apply to all three files):
- Only operate on PIDs I pass in, which were spawned by this program.
  Reject pid <= 1 and the current process's own pid.
- cgroup directory names are generated ("run-" + uuid4 hex), never built
  from user or app input.
- Never use shell=True. Never delete anything outside
  /sys/fs/cgroup/resource_engine/.

os_integration/priority.py:
- set_niceness(pid, nice, include_children=True) -> int applied. Uses
  psutil.Process.nice(). Clamp to [0, 19] unless running as root
  (negative values need root). Applies to the whole process tree.
- choose_niceness(predicted: dict) -> int: predicted cpu_pct >= 150 -> 10,
  >= 60 -> 5, else 0.
- Handle NoSuchProcess and AccessDenied without raising; return what was
  applied.

os_integration/setup_cgroup.sh (idempotent, I will run it with sudo):
- Verify /sys/fs/cgroup is cgroup2fs, else print an error and exit 1.
- mkdir -p /sys/fs/cgroup/resource_engine.
- Enable +cpu +memory in the root cgroup.subtree_control, then in
  /sys/fs/cgroup/resource_engine/cgroup.subtree_control.
- Print the resulting controllers. Do nothing destructive.

os_integration/cgroup_manager.py, class CgroupManager (base path
/sys/fs/cgroup/resource_engine, overridable for tests):
- is_available() -> bool: cgroup2fs, base path exists and is writable,
  cpu and memory controllers present. Never raises.
- create(limits) -> handle: makes a run-<uuid> directory; writes
  cpu.max as "<quota_us> 100000" (quota_us = cpu_cores * 100000) and
  memory.max in bytes (+ memory.high at 90% of memory.max so the kernel
  throttles before it kills).
- attach(handle, pid): write the pid to cgroup.procs, then also move every
  current descendant of that pid (children forked before the move would
  otherwise escape the cap).
- usage(handle) -> dict: reads memory.current, memory.peak (if present),
  cpu.stat usage_usec, and memory.events oom_kill count.
- cleanup(handle): kill any remaining pids in cgroup.procs, wait until
  the cgroup is empty, then rmdir it. Must be safe to call twice.
- Provide a context manager: `with manager.run_group(limits) as g:`.
- Limits dataclass: cpu_cores (float), memory_mb (float).
- All permission errors become a CgroupUnavailable exception with a
  helpful message ("run setup_cgroup.sh with sudo, run the API as root").

Tests: tests/test_os_integration.py. Priority tests run anywhere (spawn
`sleep 5`, check niceness changes). Cgroup tests use
pytest.mark.skipif(not CgroupManager().is_available()) and also include
pure-logic tests of the limit-to-file-value conversions that run anywhere.

Verification: `pytest tests/test_os_integration.py -q`.
Check: run sudo bash os_integration/setup_cgroup.sh, then sudo -E env "PATH=$PATH" pytest tests/test_os_integration.py -q. The cgroup tests should run, not skip. Commit.
Prompt 4.2: admission control and limits policy
TASK: os_integration/admission.py. Plan first.

- @dataclass AdmissionDecision: admitted (bool), reason (str | None),
  limits (Limits | None), niceness (int).
- decide(predicted: dict, snapshot=None) -> AdmissionDecision. The
  snapshot is a dict of system state (total/available RAM in MB, logical
  core count, current 1-minute load average); when None, read it from
  psutil. Taking it as an argument makes the function unit-testable.
- Policy, with tunables read from env vars and defaults in config.py:
  RAM_MARGIN=1.5, CPU_MARGIN=1.5, RESERVE_RAM_MB=512.
  * Refuse (admitted=False) if predicted ram_mb * RAM_MARGIN >
    available_ram_mb - RESERVE_RAM_MB. Reason string must include both
    numbers.
  * Refuse if the 1-minute load average already exceeds 90% of cores AND
    predicted cpu_pct >= 100.
  * Otherwise admit with Limits: cpu_cores = clamp(predicted cpu_pct / 100
    * CPU_MARGIN, 0.25, logical cores); memory_mb = max(64, predicted
    ram_mb * RAM_MARGIN).
  * niceness = priority.choose_niceness(predicted).
- ENFORCEMENT=off env var makes decide() always admit but still return the
  computed limits (useful for baseline comparisons).

Tests in tests/test_admission.py with hand-built snapshots: plenty of RAM
-> admitted with expected limits; low RAM -> refused with a readable
reason; high load + heavy app -> refused; light app on busy machine ->
admitted; ENFORCEMENT=off.

Verification: `pytest tests/test_admission.py -q`.
Check: read the test cases and confirm they match what you would expect a sensible scheduler to do. Commit.
Prompt 4.3: the /run-and-compare endpoint
TASK (second half of M3-T3): POST /run-and-compare in service/app.py.
Plan first, then wait for "go".

Flow, in order:
1. Validate app_name through PredictRequest. Look up the app with
   collector.config_loader.load_apps(); unknown -> 404 "Unknown app: x".
2. predicted = the active predictor (same one /predict uses).
3. decision = os_integration.admission.decide(predicted). If not
   admitted -> HTTP 409 with {"detail": decision.reason}.
4. Launch the app: subprocess.Popen with the app's command list and cwd,
   first variant, never shell=True, start_new_session=True,
   stdout/stderr to DEVNULL. If this process is root and SUDO_UID is set,
   pass user=int(SUDO_UID), group=int(SUDO_GID) so the launched app does
   NOT run as root.
5. Immediately apply enforcement to the pid:
   priority.set_niceness(pid, decision.niceness) and, if
   CgroupManager().is_available(), create a cgroup from decision.limits
   and attach the pid. If cgroups are unavailable, continue without them
   and set enforcement.cgroup_applied=False with the reason in
   enforcement.reason.
6. actual = collector.monitor.summarize(monitor_process(popen,
   timeout_s=app.timeout_s)).
7. cleanup the cgroup in a finally block, even on errors or timeouts.
8. Return RunAndCompareResponse (schemas unchanged): predicted, actual,
   duration_s, enforcement {admitted, reason, niceness, cgroup_applied}.

Concurrency: the endpoint is a plain `def` (FastAPI runs it in a
threadpool) and holds a module-level threading.Lock so only one monitored
run happens at a time; otherwise concurrent runs pollute each other's
system-wide network numbers.

Tests: tests/test_run_and_compare.py with monkeypatched
Popen/monitor/admission so no real process runs: success path, 404, 409,
cgroup unavailable path, cleanup called on exception.

Verification: `pytest -q`. Then I will run it for real; tell me the exact
command to start the server as root and a curl for cpu_burn.
Check: start the server with sudo -E env "PATH=$PATH" PREDICTOR=model uvicorn service.app:app --port 8000, then curl -s -X POST localhost:8000/run-and-compare -H 'Content-Type: application/json' -d '{"app_name":"cpu_burn"}'. You should see predicted and actual blocks plus "cgroup_applied": true. Commit.
Prompt 4.4: prove the cap actually bites
TASK: os_integration/demo_caps.py, a manual proof script (not part of
pytest). Plan first.

Run as root. It performs two experiments and prints a before/after table:
1. CPU cap: run workloads/cpu_burn.py with 4 workers for 10 seconds, (a)
   uncapped, (b) inside a cgroup with cpu_cores=0.5. Report mean CPU% from
   collector.monitor for each, and the ratio. Expect (b) near 50.
2. Memory cap: run workloads/mem_hog.py --mb 600 inside a cgroup with
   memory_mb=200. Report the exit code or signal, memory.peak, and the
   oom_kill count from memory.events. Expect the process to be killed or
   held under the cap.
3. Niceness: run two cpu_burn processes pinned to one CPU with taskset,
   one at nice 0 and one at nice 15, and report the CPU share each got.

Every experiment cleans up its cgroup even on failure. Print PASS/FAIL per
experiment with the threshold used. Exit code 0 only if all pass.
Save this output: it is the best exhibit for your final report.
Exit: /run-and-compare returns predicted and actual metrics with enforcement info, and the demo script shows a measurable CPU cap, a memory cap and a niceness effect.
Phase 5: Dashboard (about 1.5 days)
Goal: pick an app in a UI, see predicted gauges, run it, and see a predicted-vs-actual chart. Streamlit with Plotly gets all four tasks done fastest and keeps everything in Python. Run the API as root (Phase 4) and the dashboard as your normal user in a second terminal.
Prompt 5.1: API client and project structure
TASK (M4-T1): GUI skeleton and API client. Plan first, then wait for "go".

Create:
- gui/api_client.py with class ApiClient(base_url from env API_URL,
  default http://127.0.0.1:8000).
  * health() -> dict   (GET /health)
  * predict(app_name) -> dict   (POST /predict, 10 s timeout)
  * run_and_compare(app_name) -> dict   (POST /run-and-compare, 180 s
    timeout, because the app really runs)
  * Raise ApiError(status_code, message) for non-2xx responses, using the
    "detail" field of the body: 404 unknown app, 409 admission refused,
    422 validation. Raise ApiUnreachable(message) with a friendly text
    ("Is the API running? Start it with ...") on connection errors and
    timeouts. Use a requests.Session.
- gui/components/__init__.py (empty; components come in later prompts).
- gui/streamlit_app.py: page config (wide layout, title "AI Resource
  Allocation Engine"), sidebar showing API status from health() with a
  green/red indicator and the active predictor name, and a placeholder
  main area. No other features yet.
- tests/test_api_client.py: monkeypatch the session so no network is used;
  cover success, 404, 409, 422 and connection error mapping.

Verification: `pytest tests/test_api_client.py -q`, then
`streamlit run gui/streamlit_app.py`. With the API down the sidebar must
show a clear red message, not a stack trace.
Check: toggle the API on and off and watch the sidebar indicator change after a refresh. Commit.
Prompt 5.2: app picker
TASK (M4-T2): gui/components/app_picker.py. Plan first.

- render_app_picker(api: ApiClient) -> tuple[str | None, bool]: shows a
  selectbox of app names plus a "Predict" button, returns the selected app
  and whether Predict was just clicked.
- App names come from collector.config_loader.load_apps() (same machine,
  same YAML). Show the category and exe size beside the selection (small
  caption). If the YAML cannot be loaded, fall back to the app names found
  in data/sample/sample_dataset.csv and show a warning.
- On click, call api.predict(app) and store the result in
  st.session_state["prediction"] with the app name. Show a spinner while
  waiting. Map ApiError to st.error with the API's message and
  ApiUnreachable to a st.error with the friendly text. Never show a
  traceback.
- Wire it into streamlit_app.py. Until gauges exist, display the raw
  prediction as st.json.

Verification: run the app, pick two different apps and press Predict; the
JSON must differ and match what `curl /predict` returns for them.
Check: compare one result against curl by eye. Commit.
Prompt 5.3: prediction gauges
TASK (M4-T3): gui/components/prediction_gauges.py. Plan first.

- render_prediction_gauges(prediction: dict) -> None. Four Plotly
  go.Indicator gauges in one row (st.columns(4)): CPU %, RAM MB, Disk
  MB/s, Network KB/s. Each shows the numeric value with its unit.
- Gauge scales, so the needles are meaningful:
  * CPU: 0 to (logical cores * 100).
  * RAM: 0 to total system RAM in MB (psutil.virtual_memory().total).
  * Disk and network: 0 to 1.5 x the maximum value of that column in
    data/processed/dataset.csv (fall back to the sample dataset, then to a
    fixed default). Cache the scale lookup with st.cache_data.
- Colour bands: green below 50% of the scale, amber 50-80%, red above.
  Do not rely on colour alone: also print the percentage of the scale under
  each gauge.
- Keep layout readable in both light and dark Streamlit themes (transparent
  backgrounds, theme-neutral text).

Integrate it into streamlit_app.py replacing the raw JSON (keep the JSON in
an expander titled "Raw response").

Verification: run the app and predict a heavy app (gcc_build or ffmpeg)
and a light one; the gauges must clearly differ.
Prompt 5.4: predicted vs actual comparison
TASK (M4-T4): gui/components/compare_chart.py plus a "Run and compare"
button. Plan first.

1. Add a "Run and compare" button next to Predict in the app picker
   (a second return flag). Clicking it calls api.run_and_compare(app)
   inside st.spinner("Running <app>, this can take up to a minute...") and
   stores the result in st.session_state["comparison"].
2. render_compare_chart(result: dict) -> None:
   * The four metrics have different units and scales, so draw ONE
     small grouped bar chart per metric (four panels in a row via
     plotly subplots or st.columns): two bars per panel, Predicted and
     Actual, with the numeric value labelled on each bar.
   * Below it, a table: metric, predicted, actual, absolute error, error
     % ((pred - actual) / actual; show "n/a" if actual is 0).
   * Show enforcement info as small badges: admitted, niceness,
     cgroup applied (yes/no), duration_s.
3. HTTP 409 (admission refused) is not an error in the usual sense: show an
   st.warning with the reason text, and no chart.
4. Keep a history table in st.session_state of every comparison this
   session (time, app, per-metric error %). Show it in an expander.

Verification: with the API running as root, run cpu_burn and ffmpeg. The
chart, table and badges must render. Then lower RAM artificially (set the
env var RESERVE_RAM_MB very high when starting the API) and confirm the
409 warning appears.
Exit: from the browser you can select an app, see gauges, run it, and see paired bars plus an error table. Take screenshots of the gauges, the compare chart and the 409 warning now, since the report needs them. Commit "phase 5: dashboard".
Phases 6 and 7: Integration, testing and report (about 1.5 to 2 days)
Goal: prove the whole pipeline runs from a clean checkout, harden it, and write the report from real numbers. For the report prompts, the rule is that the AI may only quote numbers that exist in your files, otherwise it will invent plausible-looking results.
Prompt 6.1: Makefile and end-to-end script
TASK: one-command reproducibility. Plan first, then wait for "go".

1. Makefile with targets: setup (create .venv, pip install -r
   requirements.txt), collect (python -m collector.run_logger --runs 8),
   dataset (python -m features.build_dataset), train (python -m
   model.train --data data/processed/dataset.csv), eval (python -m
   model.evaluate), api (uvicorn service.app:app --port 8000), gui
   (streamlit run gui/streamlit_app.py), test (pytest -q), e2e (below),
   clean. Add a `help` target that lists them.
2. scripts/e2e.py that runs, in order, and stops at the first failure with
   a clear message: build_dataset -> train -> evaluate -> start the API as
   a subprocess on a free port -> wait for /health -> POST /predict for
   every app in apps_config.yaml (assert 4 non-negative floats each) ->
   if running as root with cgroups available, POST /run-and-compare for
   one short app and assert the response shape, otherwise print SKIPPED
   with the reason -> stop the API. Print a PASS/FAIL summary table.

Do not change any module under test; if something is broken, report it and
stop.

Verification: `make test` and `sudo -E env "PATH=$PATH" .venv/bin/python
scripts/e2e.py`.
Check: do a truly clean run: clone the repo into a new folder, run make setup, copy over data/raw/runs.csv, then make dataset train eval and the e2e script. Fix whatever breaks. Commit.
Prompt 6.2: test gaps and a security review
TASK: audit, then harden. Two stages, report after each.

STAGE 1 (tests): run `pytest --cov=. --cov-report=term-missing`. List every
public function and endpoint that has no test, ordered by risk. Wait for my
approval, then write the missing tests, focusing on: schema edge cases,
feature leakage, monitor handling of processes that exit early, admission
thresholds, cgroup cleanup after exceptions.

STAGE 2 (security review, do not change code yet): review the repo as a
security engineer would and give me a table of findings with file:line,
severity, and a proposed fix. Specifically check: command injection
(anything reaching subprocess), path traversal via app_name or config
values, cgroup path construction, whether the API can be made to run
arbitrary binaries (only apps from apps_config.yaml may run), privileges of
launched processes when the API runs as root, unbounded resource use in the
API (concurrent runs, huge timeouts), CORS settings, and secrets in the
repo. Wait for me to pick which fixes to apply.
Check: read the findings yourself and pick what to fix. Binding the API to 127.0.0.1 only (not 0.0.0.0) is a free fix worth keeping, since it runs apps as root. Commit.
Prompt 6.3: README
TASK: write README.md. Read the repo first and base every command on files
that actually exist; run the quick-start commands you document and confirm
they work.

Sections: What it does (3 sentences), Architecture (a Mermaid flowchart:
collector -> raw runs -> feature builder -> trainer -> model.pkl ->
predictor -> FastAPI -> admission control -> cgroups/priority, and GUI ->
FastAPI), Requirements (Linux, cgroups v2, Python version), Setup, Quick
start (make targets in order), Running the API as root and why, Dashboard,
Tests, Project layout (tree with one-line descriptions), Troubleshooting
(cgroups v1, WSL2 systemd, permission denied on cgroup.procs, app binary
missing), Known limitations.
Prompt 7.1: evaluation metrics report
TASK (M2-T4, part 1): reports/evaluation_metrics.md.

Read reports/evaluation_metrics.csv and the current
reports/evaluation_metrics.md. Rewrite the Markdown as: a one-paragraph
setup (dataset size, apps, number of runs, split schemes, models, the two
baselines), the per-target MAE / RMSE / MAE% tables for each scheme, and a
short analysis: which target is predicted best and worst, whether the model
beats the persistence baseline per target (state it explicitly with the
numbers), how leave-one-app-out compares to chronological holdout, and
what the numbers imply for choosing cgroup margins.

RULES: every number in the text must be copied from the CSV. If something
is not in the CSV, write "[not measured]" instead of estimating. No
unsupported claims about causes; label any explanation as a hypothesis.
Prompt 7.2: final report
TASK (M2-T4, part 2): reports/final_report.md.

Inputs to read first: README.md, docs/api_contract.md,
reports/evaluation_metrics.md, collector/apps_config.yaml,
data/raw/runs.csv (summary stats only), and the saved output of
os_integration/demo_caps.py (I will paste it below).

Structure:
1. Problem statement and motivation (why predict before running).
2. System architecture: Mermaid diagram plus a paragraph per stage.
3. Data collection: apps, workloads, sampling method, metric definitions,
   number of runs, how invalid runs were handled.
4. Feature engineering: schema, rolling-average design, the leakage
   precaution (first run dropped, previous runs only).
5. Model: why RandomForest multi-output, alternatives tried, hyperparameters.
6. Evaluation: embed the tables from evaluation_metrics.md and discuss.
7. OS integration: niceness policy, cgroup limits formulas with the margins,
   admission rules, and the demo_caps results as evidence.
8. Dashboard: describe each view; reference screenshots in
   reports/img/ (leave image links as placeholders I will fill).
9. Limitations: Linux-only cgroups v2; needs root or delegated cgroups;
   prediction keyed by app name only (not by input size or arguments); small
   dataset; network is system-wide not per process; run-to-run variance and
   cache effects; memory.max can OOM-kill a mis-predicted app; the
   admission decision uses a point-in-time snapshot.
10. Future work.

RULES: only use numbers present in the files above. Anything you cannot
support, write as "[TODO: needs measurement]". Keep it under 3,000 words.

DEMO OUTPUT: <paste demo_caps.py output here>
Exit: a fresh clone runs end to end, the tests pass, and both reports contain only numbers you can trace to a file. Finally, run one more prompt in a brand-new session as a grader:
You are a strict project grader. Read the repo and check each acceptance
criterion below, answering PASS, FAIL or PARTIAL with the evidence (file,
command output). Do not fix anything.
- collector/apps_config.yaml is valid YAML with binaries, paths, args and
  categories.
- monitor.py samples CPU%, RSS, disk I/O and network I/O once per second
  until the process ends.
- data/raw/runs.csv has at least 5 valid runs per app with non-zero metrics.
- features/ turns runs into model-ready features matching the schema with
  no missing values.
- model/train.py trains a multi-target regressor and saves model.pkl.
- model/evaluate.py outputs per-target MAE and RMSE on held-out data
  without errors.
- model.predict.predict(app_name) returns a dict matching the schema.
- service/schemas.py strictly validates requests and responses.
- POST /predict and POST /run-and-compare return valid responses.
- os_integration sets niceness and enforces CPU and memory caps via cgroups
  v2 for a given PID.
- The GUI has an app selector, prediction gauges and a predicted-vs-actual
  chart.
- reports/ contains evaluation_metrics.md and final_report.md covering
  problem, architecture, metrics and OS limitations.
When the AI gets stuck
Most wasted hours come from the AI repeating a failed fix or quietly changing things you did not ask for. These rules and prompts keep that cheap.
Rules:
• Three failed attempts at the same bug means stop. Run git reset --hard to the last green commit and restart the task with a sharper prompt, instead of stacking patches.
• Start a new session per phase. Long sessions drift: the AI forgets the frozen contracts and starts "improving" them.
• Ask for logging instead of guesses. "Add logging so we can see X" beats five speculative fixes.
• Point at files by path. Pasting the whole repo into the chat makes answers worse, not better.
• If a frozen file changed, undo it right away: git checkout docs/ service/schemas.py, then restate the rule.
Common failures and what usually causes them
Symptom
Likely cause
What to tell the AI
CPU% is always 0.0 in samples
A new psutil.Process object is created every tick, and the first cpu_percent() call always returns 0
"Keep Process objects in a dict across ticks and prime new ones"
Permission denied writing cgroup.procs
Not running as root, or the cpu and memory controllers are not enabled on the parent cgroup
Re-run setup_cgroup.sh with sudo, then cat /sys/fs/cgroup/resource_engine/cgroup.subtree_control
App is killed instantly under a cap
memory.max is below what the app needs, so the margin is too small
Raise RAM_MARGIN, and rely on memory.high for throttling
MAE is almost 0
Target leakage: a run's own value is inside its hist_avg_*
"Show me where shift(1) is applied and add a test for it"
Same prediction for every app
app_name is dropped and the remaining features barely differ
Print the app_profiles table and compare rows
net_kbps is noisy
psutil only offers system-wide network counters
Re-collect on a quiet machine and document it as a limitation
Tests pass but the real run fails
Everything was mocked
"Write one integration test that launches a real sleep 3 process"
Prompt templates
Bug report (fill every blank, it saves a round trip):
Something is broken.
Command I ran: <exact command>
Full output / traceback: <paste all of it>
What I expected: <one sentence>
Last green commit: <hash or message>; since then I changed: <files>

Do NOT fix anything yet. Give me 2-3 ranked hypotheses for the cause, and
for each the quickest check that would confirm or rule it out. Wait for me
to report the results.
Loop breaker (when it keeps trying variations of the same fix):
Stop. You have tried the same kind of fix twice and it failed. Write down
(1) what you tried, (2) what each attempt told us, (3) what we still do not
know. Then propose ONE different approach, or add targeted logging so we
can observe the real values. Do not edit code until I approve.
Scope-creep undo:
Show `git diff --stat`. List every file you changed that was not required
by this task and explain why you touched it. Revert those files with git
and keep only the changes the task needs.
Pre-commit review:
Review `git diff --staged` as a code reviewer. Look for: bugs, leftover
debug prints, hardcoded absolute paths, missing error handling around
psutil and file writes, anything that could run as root unnecessarily, and
missing tests. Give a list ordered by severity. Do not change anything.
Understand your own code (you will need this for a viva or demo):
Explain model/train.py as if teaching it to me: the data flow step by step,
why each design choice was made, and what would break if I changed it.
Then ask me 5 questions that test whether I understood it, one at a time,
and wait for my answer before the next.