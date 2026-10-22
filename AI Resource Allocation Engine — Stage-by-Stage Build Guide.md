# **AI Resource Allocation Engine — Stage-by-Stage Build Guide**

Predicts CPU, RAM, disk, and network requirements of an application **before it executes**, so a scheduler-like layer can make admission and placement decisions upfront instead of reacting after the fact.

## **0\. How to use this guide**

The project is split into **7 independent stages**. Each stage has its own directory, its own tech stack, and — critically — a **stub/mock mode** so it can be built and demoed without any of the other stages existing yet. This is what makes the stages independent: instead of a strict "finish stage 1 before starting stage 2" chain, every stage consumes a **fixed contract** (a schema or API shape, defined once in Section 3\) rather than the real output of the previous stage. Point it at the small sample dataset or a stub function while the real thing isn't ready, then swap the stub for the real component later with zero code changes elsewhere.

This also means the stages can be split across teammates and worked on in parallel if you're not doing this solo.

| \# | Stage | Produces | Can be built using |
| ----- | ----- | ----- | ----- |
| 1 | Data Collection | raw per-run logs | nothing — fully standalone |
| 2 | Feature Engineering | processed training dataset | the committed sample dataset |
| 3 | Prediction Model | `model.pkl` | the committed sample dataset |
| 4 | Prediction Service (API) | `/predict`, `/run-and-compare` endpoints | a mock predictor (no model needed) |
| 5 | GUI Dashboard | the app the user interacts with | the mock API endpoint |
| 6 | OS Integration (stretch) | real `nice`/cgroup enforcement | any dummy PID — no model needed |
| 7 | Evaluation & Report | final report, metrics, screenshots | whatever stages are actually done |

---

## **1\. Master directory structure**

ai-resource-allocation-engine/  
├── README.md  
├── requirements.txt  
├── .gitignore  
├── docs/  
│   └── api\_contract.md            \# the fixed schemas everything else is built against  
├── data/  
│   ├── sample/  
│   │   └── sample\_dataset.csv     \# small hand-built dataset, committed to repo  
│   ├── raw/                       \# Stage 1 output — one row per logged run  
│   └── processed/                 \# Stage 2 output — model-ready feature table  
├── collector/                     \# STAGE 1  
│   ├── monitor.py  
│   ├── run\_logger.py  
│   ├── apps\_config.yaml  
│   └── README.md  
├── features/                      \# STAGE 2  
│   ├── build\_dataset.py  
│   ├── feature\_schema.py  
│   └── README.md  
├── model/                         \# STAGE 3  
│   ├── train.py  
│   ├── evaluate.py  
│   ├── predict.py  
│   ├── artifacts/  
│   │   └── model.pkl              \# generated, gitignored  
│   └── README.md  
├── service/                       \# STAGE 4  
│   ├── app.py  
│   ├── schemas.py  
│   ├── mock\_predict.py            \# stub predictor used before model.pkl exists  
│   └── README.md  
├── gui/                           \# STAGE 5 — pick ONE  
│   ├── desktop/                   \# Tkinter / PyQt route  
│   │   └── main.py  
│   └── web/                       \# React route  
│       ├── package.json  
│       └── src/  
│           ├── App.jsx  
│           ├── api/client.js  
│           └── components/  
│               ├── AppPicker.jsx  
│               ├── PredictionGauges.jsx  
│               └── CompareChart.jsx  
├── os\_integration/                \# STAGE 6 (stretch)  
│   ├── priority.py  
│   ├── cgroup\_manager.py  
│   └── README.md  
├── reports/                       \# STAGE 7  
│   ├── evaluation\_metrics.md  
│   ├── screenshots/  
│   └── final\_report.md  
└── tests/  
    ├── test\_collector.py  
    ├── test\_features.py  
    ├── test\_model.py  
    └── test\_service.py

---

## **2\. Tech stack summary**

| Layer | Primary choice | Notes / alternative |
| ----- | ----- | ----- |
| Language | Python 3.10+ | everything except optional web GUI |
| Monitoring | `psutil`, `PyYAML` | or raw `/proc/[pid]/*` parsing on Linux |
| Data storage | CSV via `pandas`, or SQLite | Postgres if you want to over-engineer it |
| Feature/data processing | `pandas`, `numpy` |  |
| ML model | `scikit-learn` (RandomForestRegressor) | `xgboost` for a stronger baseline |
| Model serialization | `joblib` |  |
| API layer | `FastAPI` \+ `uvicorn` | Flask works fine too |
| GUI — desktop route | `PyQt5`/`PySide6` or `Tkinter` | simplest, single language, direct OS calls |
| GUI — web route | `React` \+ `Vite`, `Recharts`/`Chart.js` | reuse if you already know this stack |
| OS integration | `psutil`, Linux `cgroups` (v2), `os.nice` | Linux-only; VM or WSL2 is fine |
| Testing | `pytest` |  |
| Environment | `venv` \+ `requirements.txt` | Docker optional, not required |

---

## **3\. Shared contracts (read this before starting any stage)**

These are the fixed shapes every stage is built against. Define these first — literally create `docs/api_contract.md` with this content — so nobody has to wait on anybody else.

**Feature row schema** (input to the model — produced by Stage 2, consumed by Stage 3):

app\_name            string  
app\_category        enum\[browser, ide, compiler, media, game, other\]  
exe\_size\_mb          float  
hist\_avg\_cpu\_pct     float  
hist\_avg\_ram\_mb      float  
hist\_avg\_disk\_mbps   float  
hist\_avg\_net\_kbps    float

**Target schema** (what Stage 1 logs, what Stage 3 predicts):

cpu\_pct     float   \# peak CPU utilisation over the run  
ram\_mb      float   \# peak resident memory  
disk\_mbps   float   \# average disk throughput  
net\_kbps    float   \# average network throughput

**API contract** (Stage 4 ↔ Stage 5 — this is the boundary that makes the GUI buildable without the real model):

POST /predict  
  request:  { "app\_name": "chrome" }  
  response: { "cpu\_pct": 42.3, "ram\_mb": 850.0, "disk\_mbps": 12.4, "net\_kbps": 340.2 }

POST /run-and-compare  
  request:  { "app\_name": "chrome" }  
  response: {  
    "predicted": { "cpu\_pct": 42.3, "ram\_mb": 850.0, "disk\_mbps": 12.4, "net\_kbps": 340.2 },  
    "actual":    { "cpu\_pct": 39.1, "ram\_mb": 910.2, "disk\_mbps": 9.8,  "net\_kbps": 280.5 }  
  }

**Sample dataset** (`data/sample/sample_dataset.csv`, \~15 hand-entered rows so Stages 2–5 never have to wait on Stage 1):

app\_name,app\_category,exe\_size\_mb,hist\_avg\_cpu\_pct,hist\_avg\_ram\_mb,hist\_avg\_disk\_mbps,hist\_avg\_net\_kbps,cpu\_pct,ram\_mb,disk\_mbps,net\_kbps  
chrome,browser,210,38.0,780,10.2,300,42.3,850.0,12.4,340.2  
vlc,media,95,25.0,300,8.5,50,28.1,320.0,9.1,45.0  
gcc,compiler,40,60.0,450,25.0,5,65.2,480.0,28.3,4.0  
blender,media,650,80.0,2200,15.0,10,85.0,2350.0,17.2,8.0  
code,ide,300,20.0,600,5.0,80,23.5,650.0,6.1,90.0

---

## **Stage 1 — Data Collection Module**

**Goal:** produce real, per-run resource-usage logs for a fixed set of applications.

**Standalone readiness:** fully independent — needs nothing from any other stage.

**Tech stack:** Python, `psutil`, `PyYAML`, CSV output.

**Directory:** `collector/`

**Steps:**

`apps_config.yaml` — list the apps you'll benchmark:  
 apps:  \- name: chrome    path: /usr/bin/google-chrome    category: browser  \- name: gcc    path: /usr/bin/gcc    category: compiler    args: \["-O2", "sample.c", "-o", "sample.out"\]

1.   
2. `monitor.py` — a sampling loop: given a PID, poll `psutil.Process(pid)` once a second for `cpu_percent()`, `memory_info().rss`, `io_counters()`, and system-wide `psutil.net_io_counters()` deltas, until the process exits.  
3. `run_logger.py` — for each app in the config, launch it N times (5–10 runs recommended), attach `monitor.py`, and append one row per run to `data/raw/runs.csv` with peak/average values plus a timestamp.  
4. Run it: `python collector/run_logger.py --config apps_config.yaml --runs 8`

**Definition of done:** `data/raw/runs.csv` contains ≥5 runs for each configured app with non-zero, plausible values in all four columns.

---

## **Stage 2 — Feature Engineering**

**Goal:** turn raw per-run logs into a model-ready table matching the feature schema in Section 3\.

**Standalone readiness:** build and test this entirely against `data/sample/sample_dataset.csv`. Point it at `data/raw/runs.csv` later — same code, different input path.

**Tech stack:** `pandas`, `numpy`.

**Directory:** `features/`

**Steps:**

1. `feature_schema.py` — the column list from Section 3, in one place, so Stage 3 imports it instead of redefining it.  
2. `build_dataset.py` — reads either the sample CSV or `data/raw/runs.csv`, computes `exe_size_mb` (file size lookup), computes `hist_avg_*` columns as a rolling mean of that app's prior runs, and writes `data/processed/dataset.csv` with exactly the columns from the feature \+ target schema.  
3. Run it: `python features/build_dataset.py --input data/sample/sample_dataset.csv --output data/processed/dataset.csv`

**Definition of done:** `data/processed/dataset.csv` has no missing values and matches the schema in Section 3 column-for-column.

---

## **Stage 3 — Prediction Model**

**Goal:** a trained regressor that maps a feature row to the four target values.

**Standalone readiness:** train on `data/processed/dataset.csv` built from the sample data — you get a real (if unimpressive) model with zero dependency on Stage 1 actually running yet.

**Tech stack:** `scikit-learn` (`RandomForestRegressor` via `MultiOutputRegressor`, or one model per target), `xgboost` as an upgrade path, `joblib` for saving.

**Directory:** `model/`

**Steps:**

1. `train.py` — load `data/processed/dataset.csv`, one-hot encode `app_category`, train/test split (small dataset → use k-fold instead of a single split if you have under \~50 rows), fit the regressor, save to `model/artifacts/model.pkl` with `joblib.dump`.  
2. `evaluate.py` — compute MAE and RMSE per target column on the held-out set; print a small table. This becomes your report's results section.  
3. `predict.py` — one function: `predict(app_name: str) -> dict` that loads `model.pkl`, looks up (or accepts) the feature row for `app_name`, and returns the four predicted values in the exact JSON shape from Section 3\.

**Definition of done:** `predict("chrome")` returns a dict with all four keys populated, and `evaluate.py` prints MAE/RMSE without errors.

---

## **Stage 4 — Prediction Service (API)**

**Goal:** expose the model over HTTP so the GUI never has to import Python model code directly.

**Standalone readiness:** ship `mock_predict.py` — a function returning fixed or slightly randomized values matching the target schema — and wire the API to call it by default. Swap in `model.predict.predict()` once Stage 3 is done; nothing else changes.

**Tech stack:** `FastAPI`, `uvicorn`, `pydantic` for request/response validation.

**Directory:** `service/`

**Steps:**

1. `schemas.py` — pydantic models `PredictRequest { app_name: str }` and `PredictResponse { cpu_pct, ram_mb, disk_mbps, net_kbps }`, matching Section 3 exactly.  
2. `mock_predict.py` — `def predict(app_name: str) -> dict: return {"cpu_pct": 40.0, "ram_mb": 800.0, "disk_mbps": 10.0, "net_kbps": 300.0}` (or randomize slightly per app name so the GUI has something to visually differentiate).  
3. `app.py` — two routes:  
   * `POST /predict` → calls `predict()` (mock or real), returns `PredictResponse`.  
   * `POST /run-and-compare` → calls `predict()`, then actually launches the app using Stage 1's `monitor.py` logic to get `actual`, returns both.  
4. Run it: `uvicorn service.app:app --reload --port 8000`

**Definition of done:** `curl -X POST localhost:8000/predict -d '{"app_name":"chrome"}'` returns a valid JSON response matching the schema, using either the mock or the real model.

---

## **Stage 5 — GUI Dashboard**

**Goal:** let a user pick an app, see predicted resource needs, and optionally compare against actual usage.

**Standalone readiness:** build entirely against Stage 4's mock endpoint (`localhost:8000`). The GUI never needs to know whether it's talking to the mock or the real model — that's the point of the API contract.

**Pick one route:**

**Option A — Desktop (`gui/desktop/`)**

* Tech: `PyQt5`/`PySide6` or `Tkinter`.  
* `main.py`: a dropdown/combobox of app names, a "Predict" button that calls the API (`requests.post`) and renders four progress bars/gauges, and a "Run & compare" button that calls `/run-and-compare` and renders predicted vs. actual as paired bars.  
* Advantage: can call `os_integration/` (Stage 6\) functions directly, in-process, no HTTP hop needed for the OS-integration demo.

**Option B — Web (`gui/web/`)**

* Tech: `React` \+ `Vite`, `Recharts` or `Chart.js`, plain `fetch`/`axios` to call the API.  
* `components/AppPicker.jsx` — dropdown \+ predict button.  
* `components/PredictionGauges.jsx` — four gauge/bar visuals bound to the `/predict` response.  
* `components/CompareChart.jsx` — grouped bar chart bound to the `/run-and-compare` response.  
* `api/client.js` — one file wrapping the two endpoint calls, so the base URL (mock vs. real) is a single constant to change.

**Definition of done:** selecting an app and clicking Predict renders all four values without errors, whether the API is running in mock or real mode.

---

## **Stage 6 — OS Integration (stretch goal)**

**Goal:** actually act on a prediction — set process priority or cap resources — closing the loop from "AI prediction" to "operating systems."

**Standalone readiness:** fully independent — test against any running process's PID, no model or prediction needed at all.

**Tech stack:** `psutil`, Linux `cgroups` v2 (needs a Linux host, VM, or WSL2).

**Directory:** `os_integration/`

**Steps:**

1. `priority.py` — `def set_priority(pid: int, predicted_cpu_pct: float)`: if predicted CPU is high, lower niceness urgency appropriately via `psutil.Process(pid).nice(value)`; log the before/after niceness.  
2. `cgroup_manager.py` — create a cgroup with a `memory.max` / `cpu.max` set from the predicted RAM/CPU values, and move the target PID into it (`echo $PID > cgroup.procs`), wrapped in Python via `subprocess` or a `cgroups` helper library.  
3. Wire it in: from the GUI or the API's `/run-and-compare` route, call `set_priority()`/cgroup assignment right before actually launching the app, using the *predicted* values from Stage 3/4.

**Definition of done:** you can show, live, that a process launched through your engine actually has a different niceness value or cgroup limit than one launched normally (`ps -o pid,ni` or `cat /sys/fs/cgroup/.../memory.max`).

---

## **Stage 7 — Evaluation & Report**

**Goal:** the artifact you actually submit.

**Standalone readiness:** write this against whatever stages are complete — it doesn't block on anything, but it's obviously most convincing once Stages 1–5 (and ideally 6\) exist.

**Directory:** `reports/`

**Contents:**

* `evaluation_metrics.md` — MAE/RMSE per target from Stage 3's `evaluate.py`, plus a short table of predicted-vs-actual for a handful of real runs from `/run-and-compare`.  
* `screenshots/` — GUI screenshots showing a prediction and a predicted-vs-actual comparison.  
* `final_report.md` — problem statement (proactive vs. reactive resource management), architecture diagram, tech stack, stage-by-stage summary, results, limitations (small dataset, fixed app set), and the OS-integration stretch goal if you built it.

**Definition of done:** a reader who never saw your code can understand what the system does, how well it predicts, and what OS-level effect it has, purely from this folder.

---

## **Appendix — running the whole thing together**

python \-m venv venv && source venv/bin/activate  
pip install \-r requirements.txt

\# 1\. collect data (or skip and use data/sample/sample\_dataset.csv)  
python collector/run\_logger.py \--config collector/apps\_config.yaml \--runs 8

\# 2\. build features  
python features/build\_dataset.py \--input data/raw/runs.csv \--output data/processed/dataset.csv

\# 3\. train  
python model/train.py  
python model/evaluate.py

\# 4\. start the API (point service/app.py at model.predict instead of mock\_predict)  
uvicorn service.app:app \--reload \--port 8000

\# 5\. start the GUI  
python gui/desktop/main.py  
\# — or —  
cd gui/web && npm install && npm run dev

