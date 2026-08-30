# vadgr 0.4.12 harness

These helpers observe the installation boundary. They do not install, start,
stop, configure or drive vadgr.

- `snapshot-unix.sh LABEL OUTPUT` records hashes for shell profiles, Python and
  uv user caches, selected Python environment variables and network
  configuration on Linux, WSL and macOS.
- `snapshot-windows.ps1 -Label LABEL -Output OUTPUT` records the matching
  Windows hashes, including the current-user Python registry tree.

The files contain hashes and presence markers, not credential values. Run them
from this committed directory so every host uses the same observation.
