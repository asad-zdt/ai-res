# Minimal Plan: Add Linux Support to Existing Project

## 1. Goal
Make the existing project run smoothly on Linux without altering the current Windows functionality, API endpoints, or existing Tkinter GUI structure.

## 2. Execution Steps

### Step 1: Platform Detection & Conditional Imports
* In files that import Windows-only libraries (like `pywin32` / `win32job`), add conditional imports using `sys.platform`.
* Ensure importing these modules on Linux does not throw an `ImportError`.

### Step 2: Implement Linux Enforcement Branches
* In the existing enforcement logic (where CPU and memory limits are set):
  * **Windows Branch (Unchanged):** Continue using Windows Job Objects and Priority Classes when `sys.platform == "win32"`.
  * **Linux Branch (New):**
    1. **Priority/Niceness:** Set process priority using `psutil.Process(pid).nice(val)` when running on Linux.
    2. **cgroups v2:** Write resource constraints to `/sys/fs/cgroup/` (setting `cpu.max` and `memory.max`) if the directory exists and write permissions are available. Fall back gracefully to niceness if cgroups are unavailable or non-root.

### Step 3: Path & Executable Resolution
* Update any hardcoded Windows paths (e.g., `C:\...`) in workload configuration files to rely on `shutil.which()` or system `$PATH` lookups so executables (like `gcc`, `ffmpeg`, or `python`) are resolved dynamically on Linux (`/usr/bin/...`).

### Step 4: Verification
* Run the existing API and Tkinter GUI on Windows to confirm no regressions.
* Run the project on Linux/WSL2 to verify that workloads execute, metrics are collected, and nice levels/cgroups are applied correctly.