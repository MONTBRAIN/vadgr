"""Security utilities for the registry module.

Centralizes all security checks: zip extraction safety, URL validation,
integrity verification, and token resolution.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import ssl
import zipfile
from pathlib import Path
from urllib.parse import urlparse

# --- Zip safety constants ---

# Maximum decompressed size: 500 MB
MAX_UNCOMPRESSED_SIZE = 500 * 1024 * 1024

# Maximum number of files in a .agnt archive
MAX_FILE_COUNT = 5000

# Maximum path length for entries inside the zip
MAX_ZIP_PATH_LENGTH = 255


# --- URL validation constants ---

# Allowed URL schemes for downloads
_ALLOWED_SCHEMES = frozenset({"https", "http"})

# Private/reserved IP ranges that should never be download targets
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]


def safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract a zip file safely, preventing zip slip and zip bombs.

    Validates every entry before extracting:
    - No path traversal (../ or absolute paths)
    - Total uncompressed size within limits
    - File count within limits
    - No symlinks in the archive

    Args:
        zf: An open ZipFile object.
        dest: Target directory for extraction.

    Raises:
        ValueError: If the archive contains unsafe entries.
    """
    dest = dest.resolve()
    total_size = 0
    entries = zf.infolist()

    if len(entries) > MAX_FILE_COUNT:
        raise ValueError(
            f"Archive contains {len(entries)} files, exceeds limit of {MAX_FILE_COUNT}"
        )

    for info in entries:
        # Check for symlinks (external_attr bit 0x120000 on Unix)
        if info.external_attr >> 16 & 0o170000 == 0o120000:
            raise ValueError(
                f"Archive contains symlink: {info.filename!r} -- symlinks are not allowed"
            )

        # Check path length
        if len(info.filename) > MAX_ZIP_PATH_LENGTH:
            raise ValueError(
                f"Archive entry path too long ({len(info.filename)} chars): "
                f"{info.filename[:80]!r}..."
            )

        # Normalize and validate path
        member_path = Path(info.filename)

        # Block absolute paths
        if member_path.is_absolute():
            raise ValueError(
                f"Archive contains absolute path: {info.filename!r}"
            )

        # Block path traversal
        if ".." in member_path.parts:
            raise ValueError(
                f"Archive contains path traversal: {info.filename!r}"
            )

        # Resolve the final extraction path and verify it stays under dest
        target = (dest / member_path).resolve()
        if not str(target).startswith(str(dest)):
            raise ValueError(
                f"Archive entry escapes target directory: {info.filename!r}"
            )

        # Accumulate decompressed size
        total_size += info.file_size
        if total_size > MAX_UNCOMPRESSED_SIZE:
            raise ValueError(
                f"Archive uncompressed size exceeds {MAX_UNCOMPRESSED_SIZE // (1024 * 1024)} MB limit"
            )

    # All checks passed -- extract
    dest.mkdir(parents=True, exist_ok=True)
    for info in entries:
        target = (dest / info.filename).resolve()
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hex digest of a file.

    Reads in 64KB chunks to handle large files without loading into memory.
    """
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def verify_sha256(file_path: Path, expected_hash: str) -> bool:
    """Verify a file's SHA256 hash matches the expected value.

    Args:
        file_path: Path to the file to verify.
        expected_hash: Expected hex digest (lowercase).

    Returns:
        True if hash matches.

    Raises:
        ValueError: If hash does not match (includes both hashes for debugging).
    """
    actual = compute_sha256(file_path)
    if actual != expected_hash.lower():
        raise ValueError(
            f"Integrity check failed for {file_path.name}: "
            f"expected sha256={expected_hash}, got sha256={actual}"
        )
    return True


def validate_download_url(url: str, *, allow_private: bool = False) -> str:
    """Validate a download URL for safety.

    Checks:
    - Scheme is http or https (blocks file://, ftp://, etc.)
    - Hostname is not a private/reserved IP (anti-SSRF)
    - No user:password in URL

    Args:
        url: The URL to validate.
        allow_private: If True, skip private IP check (for local dev/testing).

    Returns:
        The validated URL string.

    Raises:
        ValueError: If the URL fails any safety check.
    """
    parsed = urlparse(url)

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Unsupported URL scheme: {parsed.scheme!r}. "
            f"Only {', '.join(sorted(_ALLOWED_SCHEMES))} are allowed."
        )

    if not parsed.hostname:
        raise ValueError(f"URL has no hostname: {url!r}")

    # Block credentials in URL
    if parsed.username or parsed.password:
        raise ValueError(
            "URLs with embedded credentials are not allowed"
        )

    # Anti-SSRF: block private/reserved IPs
    if not allow_private:
        try:
            addr = ipaddress.ip_address(parsed.hostname)
            for network in _PRIVATE_NETWORKS:
                if addr in network:
                    raise ValueError(
                        f"URL points to private/reserved IP {parsed.hostname} -- "
                        f"this is blocked to prevent SSRF attacks"
                    )
        except ValueError as e:
            if "SSRF" in str(e):
                raise
            # Not an IP literal -- it's a hostname, which is fine.
            # DNS rebinding is a separate concern handled at the network layer.

    return url


def validate_local_path(path: Path, root: Path) -> Path:
    """Validate that a path stays within a root directory.

    Resolves symlinks and ../ to prevent path traversal.

    Args:
        path: The path to validate (can be relative to root).
        root: The root directory that path must stay within.

    Returns:
        The resolved absolute path.

    Raises:
        ValueError: If the path escapes root.
    """
    resolved = (root / path).resolve()
    root_resolved = root.resolve()

    if not str(resolved).startswith(str(root_resolved) + os.sep) and resolved != root_resolved:
        raise ValueError(
            f"Path traversal detected: {path!r} resolves to {resolved}, "
            f"which is outside {root_resolved}"
        )
    return resolved


def resolve_token(value: str | None) -> str:
    """Resolve a token value that may reference an environment variable.

    Supports:
        $ENV_VAR
        ${ENV_VAR}
        literal values (returned as-is)

    Args:
        value: The token string from config.

    Returns:
        The resolved token value (may be empty string if env var not set).
    """
    if not value:
        return ""

    # Match $VAR or ${VAR}
    match = re.match(r"^\$\{([^}]+)\}$", value) or re.match(r"^\$([A-Za-z_][A-Za-z0-9_]*)$", value)
    if match:
        env_name = match.group(1)
        return os.environ.get(env_name, "")

    return value


def create_ssl_context(*, verify: bool = True) -> ssl.SSLContext:
    """Create an SSL context for HTTPS connections.

    Args:
        verify: If True (default), verify server certificates.
                Set to False only for testing with self-signed certs.

    Returns:
        Configured SSLContext.
    """
    if verify:
        ctx = ssl.create_default_context()
        # Enforce minimum TLS 1.2
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    else:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx
