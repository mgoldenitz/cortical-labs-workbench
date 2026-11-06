# Redaction note

The files in this folder were copied from the evidence runs of 2026-11-06 at commit `251d6cf` and then edited in one way before publication. Every occurrence of the container scratch directory used as the evidence root

```
/tmp/claude-0/-home-user-cortical-labs-workbench/<session id>/scratchpad/ev3
```

was replaced by the literal text `<evidence>`. The directory name contained a local session identifier and has no meaning outside that container. Nothing else was changed: no measurement, digest, status, timestamp or checksum value was edited, and the files not listed below are byte-for-byte copies of the run output.

## Files edited after the run

Each listed file held the prefix the given number of times, in log lines or in a `run_dir` or `recording_path` field. The seven JSON files still parse as JSON.

| File | Replacements | SHA-256 as produced by the run | SHA-256 as published |
| --- | --- | --- | --- |
| `py313/pytest.log` | 2 | `b1da7d0e8b83eb6fb8bd2bd165ae0b8e372e60e049dd54f57d51c297017daebd` | `a8f510e53b703c761f306a67a486a8f049474694405ffc4e5dc9d08e845a0d38` |
| `py313/runs.log` | 6 | `692ce110fa6ae7c6be9b442886a088a5493083593d3fba64a67f1cea4223793e` | `a45a8cb377494d11849752964ae1f7a34653b7311982b14edcb13e3315055fc6` |
| `py313/known-issue.log` | 2 | `c0648240734aa4086ea484ac4c0a5286532c792c1bc36b22763cb5f8abebf2de` | `bed9ae3f7d9587f76bfca4f000100315a3d1737e3d3ceb9e0bf04b0934d766c1` |
| `py313/known-issue-run/manifest.json` | 1 | `21d86b0837e05e756cae42bca61616167d24937e76fbbc2c87100e64ee30e089` | `42e0b65377c17413e0ba04588944afe59bb0f207ecf4b6c9f74f39bbfaa0885b` |
| `py313/known-issue-run/worker_result.json` | 1 | `d4e968c87fe3c3b82cc216ae936fc54b0f401f761b83160854de8346f2a4e6f4` | `c22eb465408967ac51b44fb4a46ddf2d4ccdabd25d8981b609ccf0aa43e320af` |
| `py312/pytest.log` | 2 | `16ee834db1953aa8cc341a38c0f71e5c21df8a40a65e109c4b47d3995f97af57` | `53e72017e6188d074a151063f54ee11b982217e149c3da0930c0208145f0c4d4` |
| `py312/runs.log` | 6 | `fa1b05445afc19c023133730909ab27341d66521b02dcf898d2dd4772d26fc74` | `f9fc7cb884a47d4e9e263588b1bea160ed7cec1d56bb8adad25e6b11bb209c70` |
| `py312/known-issue.log` | 2 | `b50898f1892cb4bd6805f12155a6fcbb66d73f0f250482732ce64be6d1648323` | `0b46bf2ae3a5e341ace708c3ed63e0dea319226dbf19f80ae7c299500d7bc3cd` |
| `py312/known-issue-run/manifest.json` | 1 | `9e5e027610f75ab68eb735b79162e84e381c44925f50a043df38965e155bb9ba` | `d840651fe78137e054555952a0382481c0e96d8b4b83fdbaa1910eca71aead07` |
| `py312/known-issue-run/worker_result.json` | 1 | `168ef32d226a61ee348d5ae2bf18e921621383b689ee8f2fb1bf3b4c321a963f` | `49059bbf86ac921161d648f66bbca8e9956ed4b5f7693b253ef6df2dc22b1961` |
| `sample-run/config.json` | 1 | `6562c62350021474289c8d00124ab04ba9f633203aabdd8208d823a69089c550` | `a71d79c4e03a0050eb9b40e55d72f7a84aa797bafd499264cb2d61290a4778e0` |
| `sample-run/manifest.json` | 1 | `1c37175e1bd4a67998e5cc11c9eaad4b0caa7cedc09f4fde33dfd06dc3640e4d` | `e2dba5cdb6c85ba13a3ea8afa1d8db9fd0fc678e49e6406b905f70329e7242b2` |
| `sample-run/worker_result.json` | 1 | `f781aefc5a27f51233a64b1892e1f57e650753f50509b89dca568fd6528c59f2` | `61ee08c3ea9762315b5e55082828c9ba38abfd46bc2961ae86722bb015b32cac` |

## Why the manifests no longer match some files

Each `manifest.json` keeps the checksums its run wrote, so it still describes the original run output. Those checksums were left alone on purpose. `config.json` and `worker_result.json` were edited afterwards, so their listed checksums no longer match the published copies; the third column above matches the manifest. A `manifest.json` does not list a checksum for itself, and the logs outside the run folders are not listed in any manifest. The other files in `sample-run/` (`channel_metrics.csv`, `metrics.json`, `report.html`, `worker.log`) are unedited and still match their manifest entries.

[`SHA256SUMS`](SHA256SUMS) lists the checksums of every published file in this folder, as published. Check it from this folder with `sha256sum -c SHA256SUMS`.

## Partial bundles and `workbench verify`

`sample-run/` is a partial bundle: it has every output of the run except `recording.h5` (16.6 MB). `py313/known-issue-run/` and `py312/known-issue-run/` hold only the manifest, worker log and worker result. `workbench verify` supports only complete run folders. It checks every file listed in the manifest and recomputes the canonical digests from `recording.h5`, so on these bundles it reports the missing files and the checksum mismatches above, exits with code 1, and cannot check the canonical digests. To verify a complete run, produce one with the commands in [`../reproducing.md`](../reproducing.md) and run `workbench verify` on that folder.
