"""vadgr native agent loop.

A top-level package (peer of ``api``/``cli``/``forge``): the provider-agnostic
agent loop and the abstractions every provider reuses. It owns the conversation
history -- so it can prune old screenshots (keep-last-N) and the wire-limit
failure class simply cannot recur. It imports nothing from ``api``.

See ``design/vadgr/0.4.0/native-loop.md`` for the build spec.
"""
