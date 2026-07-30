"""Auth strategies: how a provider proves who it is on the wire.

The ``AuthStrategy`` port (``base.py``) plus the three shipped strategies a
provider composes by reference: ``OAuthStrategy`` (``oauth.py`` -- token cache,
refresh, per-OS store), ``APIKeyStrategy`` (``api_key.py``), and
``NoAuthStrategy`` (``none.py``).
"""
