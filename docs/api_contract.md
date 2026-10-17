# API Contract

## Feature schema

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `app_name` | string | — | Configured application identifier used for lookup |
| `app_category` | string | — | Application category from the application configuration |
| `exe_size_mb` | float | MB | Size of the application's executable |
| `hist_avg_cpu_pct` | float | % | Historical mean CPU usage for the application |
| `hist_avg_ram_mb` | float | MB | Historical mean resident memory usage for the application |
| `hist_avg_disk_mbps` | float | MB/s | Historical mean disk read-and-write throughput |
| `hist_avg_net_kbps` | float | KB/s | Historical mean system-wide network throughput while the application ran |

Feature columns must be supplied in this order:
`app_name`, `app_category`, `exe_size_mb`, `hist_avg_cpu_pct`,
`hist_avg_ram_mb`, `hist_avg_disk_mbps`, `hist_avg_net_kbps`.

## Target schema

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `cpu_pct` | float | % | Mean summed CPU usage of the whole process tree during the run; can exceed 100% on multi-core systems |
| `ram_mb` | float | MB | Peak resident set size summed over the whole process tree |
| `disk_mbps` | float | MB/s | Mean read-and-write disk throughput of the whole process tree during the run |
| `net_kbps` | float | KB/s | Mean system-wide network throughput during the run |

Target columns must be supplied in this order: `cpu_pct`, `ram_mb`,
`disk_mbps`, `net_kbps`.

## Metric definitions and limitations

- `cpu_pct` is the mean of summed CPU% over the whole process tree during the
  run. It can exceed 100 on multi-core systems.
- `ram_mb` is the peak resident set size summed over the process tree.
- `disk_mbps` is the mean (read + write) MB/s of the process tree.
- `net_kbps` is the mean system-wide network KB/s during the run. `psutil` has
  no per-process network counters, so this is a known limitation.

## Endpoints

### `POST /predict`

Request:

```json
{"app_name": "chrome"}
```

Response:

```json
{
  "app_name": "chrome",
  "predicted": {
    "cpu_pct": 35.2,
    "ram_mb": 820.5,
    "disk_mbps": 1.4,
    "net_kbps": 210.0
  },
  "source": "model"
}
```

`source` is either `"model"` or `"mock"`.

### `POST /run-and-compare`

Request:

```json
{"app_name": "chrome"}
```

Response:

```json
{
  "app_name": "chrome",
  "predicted": {
    "cpu_pct": 35.2,
    "ram_mb": 820.5,
    "disk_mbps": 1.4,
    "net_kbps": 210.0
  },
  "actual": {
    "cpu_pct": 32.8,
    "ram_mb": 790.0,
    "disk_mbps": 1.2,
    "net_kbps": 205.0
  },
  "duration_s": 12.5,
  "enforcement": {
    "admitted": true,
    "reason": null,
    "niceness": 0,
    "cgroup_applied": true
  }
}
```

## Errors

- `404`: `{"detail": "Unknown app: <name>"}` when the application is not
  present in `collector/apps_config.yaml`.
- `422`: Request validation error.
- `409`: Admission control refused the launch.

## Platform notes

- On Windows, per-process I/O counters include all I/O performed by a process,
  including files, pipes, network, and devices. Consequently, measured
  `disk_mbps` can overstate actual disk traffic for applications that also use
  the network.
- `net_kbps` is measured from system-wide network counters. `psutil` does not
  provide per-process network counters, so the measurement can include traffic
  from other applications.
- On Windows, `cgroup_applied` means a Job Object with CPU and memory caps was
  applied to the launched process.
