# dist/

This directory holds built and released artifacts produced outside of the normal
development workflow. It is intentionally empty in the repository.

## What goes here

- **Docker image tarballs** exported via `docker save`, e.g.:
  ```bash
  docker save polyschnack-asr:cpu | gzip > dist/polyschnack-asr-cpu-v1.0.tar.gz
  docker save polyschnack-webapp:latest | gzip > dist/polyschnack-webapp-v1.0.tar.gz
  ```
- **GitHub release packages** — any `zip`/`tar.gz` bundles created for a versioned release.
- **Pre-built ONNX model snapshots** if distributed separately from HuggingFace.

## What does NOT go here

- Source code changes — those live in `approach-a/`, `webapp/`, etc.
- Model weights downloaded at runtime — those go into the `polyschnack-models` docker volume.
- Benchmark outputs — those live in `results/`.

## .gitignore behaviour

`dist/*` is git-ignored except for this `README.md` and the `.gitkeep` marker.
Large binary artifacts should never be committed to the repository; upload them
to GitHub Releases or an object store instead.
