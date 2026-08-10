"""vadgr native agent loop.

A top-level package (peer of ``api`` and ``cli``): the provider-agnostic
agent loop and the abstractions every provider reuses. It owns the conversation
history -- so it can prune old screenshots (keep-last-N) and the wire-limit
failure class simply cannot recur. It imports nothing from ``api``.
"""
