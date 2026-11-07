# Known issues

## Accelerated mode loses the start of recordings longer than about 5 s

Observed in the tested environment only. Not reported upstream yet, and the cause is not confirmed.

### Environment

- cl-sdk 1.0.0 from PyPI (source commit `a9a2f9c0cefaa032075d7cd7ccbbc4b037ba1991`)
- Python 3.13.18, Linux x86_64 (kernel 6.18.44), 4 CPUs, 15 GiB RAM, cloud container
- Simulator random source, `CL_SDK_RANDOM_SEED=42`, `CL_SDK_REPLAY_START_OFFSET=0`, `CL_SDK_VISUALISATION=0`
- Packages as pinned in `requirements-lock.txt`
- Dates: 2026-11-06

### What happens

With `CL_SDK_ACCELERATED_TIME=1`, a 10 s recording prints

```
Recording fell behind ring buffer (cursor=0, buf_start=118928). Some data was lost.
```

and the file has 131,072 sample rows although `duration_frames` is 250,000. The rows that are kept are the end of the recording, not the start: the first spike in the file is at frame 119,134, yet the file still says `start_timestamp = 0`, so the data is shifted relative to its timestamps.

| Window | Mode | Runs | Result |
| --- | --- | --- | --- |
| 1 s, 3 s, 5 s | accelerated | many (tests, smoke runs) | complete |
| 10 s | accelerated | 7 (3 raw SDK, 4 workbench) | data lost every time; 131,072 rows kept in each run checked |
| 30 s | accelerated | 2 (workbench) | data lost; 616,881 and 617,905 of 750,001 rows kept |
| 10 s | wall clock | 3 (2 raw SDK, 1 workbench) | complete |
| 30 s | wall clock | 1 | complete |

Hypothesis, not verified: the simulator's ring buffer holds about 131,072 frames (2^17, 5.24 s at 25 kHz), and in accelerated mode the data producer runs that far ahead before the recording process starts reading.

### How the workbench handles it

Wall-clock mode is the default. With `--accelerated`, a run that hits this problem fails three error-level checks (`rows_match_duration`, `window_covered`, `no_ring_buffer_overrun`), is marked `incomplete` in its manifest, report and console output, keeps all its files, and exits with code 2. The `start_aligned` check does not catch it, because the file's `start_timestamp` is still 0.

### Reproduce

Raw SDK, without the workbench (from a scratch directory containing an empty `rec/` folder):

```bash
CL_SDK_RANDOM_SEED=42 CL_SDK_REPLAY_START_OFFSET=0 CL_SDK_ACCELERATED_TIME=1 CL_SDK_VISUALISATION=0 \
  python /path/to/cortical-labs-workbench/discovery/rec10.py
# Recording fell behind ring buffer (cursor=0, buf_start=118928). Some data was lost.
# duration_frames 250000 samples rows 131072 spikes 370

CL_SDK_RANDOM_SEED=42 CL_SDK_REPLAY_START_OFFSET=0 CL_SDK_ACCELERATED_TIME=0 CL_SDK_VISUALISATION=0 \
  python /path/to/cortical-labs-workbench/discovery/rec10.py
# duration_frames 250000 samples rows 250000 spikes 699
```

With the workbench:

```bash
workbench run --seconds 10 --accelerated   # status INCOMPLETE, exit code 2
workbench run --seconds 10                 # status COMPLETE
```

Both reproductions were last run on 2026-11-06 with the output shown.

### Not yet tested

Other operating systems, other CPU counts, cl-sdk versions other than 1.0.0, and window lengths between 5 s and 10 s.
