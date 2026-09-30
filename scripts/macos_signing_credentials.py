#!/usr/bin/env python3
"""Run one protected signing command with temporary macOS credentials.

The workflow owns source approval and environment protection. Runner markers
prevent accidental workstation use; they are not an authorization mechanism.
No production credential is passed to a subprocess as a command argument.
"""

import base64
import binascii
import ctypes as C
import hashlib
import os
from pathlib import Path
import plistlib
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time


SECRET_NAMES = (
    "MACOS_APPLICATION_P12_BASE64", "MACOS_APPLICATION_P12_PASSWORD",
    "MACOS_INSTALLER_P12_BASE64", "MACOS_INSTALLER_P12_PASSWORD",
    "MACOS_NOTARY_PRIVATE_KEY", "MACOS_NOTARY_KEY_ID", "MACOS_NOTARY_ISSUER_ID",
)


class SigningError(Exception):
    """A deliberately non-secret diagnostic suitable for a workflow log."""


def require_runner(env):
    if (sys.platform != "darwin" or env.get("GITHUB_ACTIONS") != "true"
            or env.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or env.get("GITHUB_REPOSITORY") != "MONTBRAIN/vadgr"):
        raise SigningError("Credentials require the GitHub-hosted macOS signing job.")
    if env.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}:
        raise SigningError("This workflow event cannot load signing credentials.")


class ImportParameters(C.Structure):
    _fields_ = [("version", C.c_uint32), ("flags", C.c_uint32),
                ("passphrase", C.c_void_p), ("alertTitle", C.c_void_p),
                ("alertPrompt", C.c_void_p), ("accessRef", C.c_void_p),
                ("keyUsage", C.c_void_p), ("keyAttributes", C.c_void_p)]


class KeychainSettings(C.Structure):
    _fields_ = [("version", C.c_uint32), ("lockOnSleep", C.c_ubyte),
                ("useLockInterval", C.c_ubyte), ("lockInterval", C.c_uint32)]


class NativeSecurity:
    """Small bindings for the file keychain used by Apple's signing tools."""

    def __init__(self):
        require_runner(os.environ)
        self.refs = []
        self.cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.sec = C.CDLL("/System/Library/Frameworks/Security.framework/Security")
        p, u, b, n = C.c_void_p, C.c_uint32, C.c_ubyte, C.c_long
        out = C.POINTER(p)
        definitions = {
            "CFRelease": (None, [p]), "CFGetTypeID": (C.c_ulong, [p]),
            "CFStringCreateWithCString": (p, [p, C.c_char_p, u]),
            "CFDataCreate": (p, [p, p, n]), "CFDataGetLength": (n, [p]),
            "CFDataGetBytePtr": (p, [p]),
            "CFArrayCreate": (p, [p, C.POINTER(p), n, p]),
            "CFArrayGetCount": (n, [p]), "CFArrayGetValueAtIndex": (p, [p, n]),
        }
        for name, (result, arguments) in definitions.items():
            self.bind(self.cf, name, result, arguments)
        definitions = {
            "SecKeychainCopySearchList": (C.c_int32, [out]),
            "SecKeychainCopyDefault": (C.c_int32, [out]),
            "SecKeychainSetSearchList": (C.c_int32, [p]),
            "SecKeychainSetDefault": (C.c_int32, [p]),
            "SecKeychainCreate": (C.c_int32, [C.c_char_p, u, p, b, p, out]),
            "SecKeychainUnlock": (C.c_int32, [p, u, p, b]),
            "SecKeychainSetSettings": (C.c_int32, [p, C.POINTER(KeychainSettings)]),
            "SecKeychainDelete": (C.c_int32, [p]),
            "SecKeychainSetUserInteractionAllowed": (C.c_int32, [b]),
            "SecTrustedApplicationCreateFromPath": (C.c_int32, [C.c_char_p, out]),
            "SecAccessCreate": (C.c_int32, [p, p, out]),
            "SecItemImport": (C.c_int32, [p, p, C.POINTER(u), C.POINTER(u), u,
                                         C.POINTER(ImportParameters), p, out]),
            "SecIdentityGetTypeID": (C.c_ulong, []),
            "SecIdentityCopyCertificate": (C.c_int32, [p, out]),
            "SecIdentityCopyPrivateKey": (C.c_int32, [p, out]),
            "SecCertificateCopyData": (p, [p]),
            "SecKeychainItemCopyAccess": (C.c_int32, [p, out]),
            "SecAccessCopyMatchingACLList": (p, [p, p]),
            "SecACLCopyContents": (C.c_int32, [p, out, out, C.POINTER(u)]),
            "SecACLSetContents": (C.c_int32, [p, p, p, u]),
            "SecKeychainItemSetAccessWithPassword": (C.c_int32, [p, p, u, p]),
        }
        for name, (result, arguments) in definitions.items():
            self.bind(self.sec, name, result, arguments)
        self.check(self.sec.SecKeychainSetUserInteractionAllowed(False), "disable prompts")

    @staticmethod
    def bind(library, name, result, arguments):
        try:
            function = getattr(library, name)
        except AttributeError:
            raise SigningError("The runner lacks a required Security framework API.") from None
        function.restype = result
        function.argtypes = arguments

    @staticmethod
    def check(status, operation):
        if status:
            raise SigningError(f"Security framework {operation} failed (OSStatus {status}).")

    def retain_result(self, value):
        value = value.value if isinstance(value, C.c_void_p) else value
        if not value:
            raise SigningError("Security framework returned an empty object.")
        self.refs.append(value)
        return value

    def copied(self, name, *args):
        result = C.c_void_p()
        self.check(getattr(self.sec, name)(*args, C.byref(result)), name)
        return self.retain_result(result)

    def string(self, value):
        return self.retain_result(self.cf.CFStringCreateWithCString(None, value.encode(), 0x08000100))

    def array(self, values):
        # Objects remain owned by this session, so the array needs no callbacks.
        pointers = (C.c_void_p * len(values))(*values)
        return self.retain_result(self.cf.CFArrayCreate(None, pointers, len(values), None))

    def values(self, array):
        return [self.cf.CFArrayGetValueAtIndex(array, i)
                for i in range(self.cf.CFArrayGetCount(array))]

    def snapshot(self):
        return (self.copied("SecKeychainCopySearchList"),
                self.copied("SecKeychainCopyDefault"))

    def create(self, path, password):
        return self.copied("SecKeychainCreate", os.fsencode(path), len(password), password, False, None)

    def restrict_search(self, keychain):
        self.check(self.sec.SecKeychainSetSearchList(self.array([keychain])), "set search list")

    def import_identity(self, keychain, payload, password, keychain_password):
        self.check(self.sec.SecKeychainUnlock(keychain, len(keychain_password), keychain_password, True), "unlock")
        settings = KeychainSettings(1, False, True, 21600)
        self.check(self.sec.SecKeychainSetSettings(keychain, C.byref(settings)), "set lock interval")
        trusted = [self.copied("SecTrustedApplicationCreateFromPath", path)
                   for path in (None, b"/usr/bin/codesign", b"/usr/bin/pkgbuild",
                                b"/usr/bin/productbuild", b"/usr/bin/productsign")]
        access = self.copied("SecAccessCreate", self.string("Vadgr temporary signing"), self.array(trusted))
        usage = self.array([C.c_void_p.in_dll(self.sec, "kSecAttrCanSign").value])
        attributes = self.array([C.c_void_p.in_dll(self.sec, name).value
                                 for name in ("kSecAttrIsPermanent", "kSecAttrIsSensitive")])
        # Import only one key. Omitting kSecAttrIsExtractable prevents later
        # export from this temporary keychain, including wrapped export.
        params = ImportParameters(0, 1, self.string(password), None, None, access, usage, attributes)
        data = self.retain_result(self.cf.CFDataCreate(None, payload, len(payload)))
        format_, type_ = C.c_uint32(12), C.c_uint32(5)  # PKCS12, aggregate
        imported = self.copied("SecItemImport", data, None, C.byref(format_), C.byref(type_),
                               0, C.byref(params), keychain)
        identities = [item for item in self.values(imported)
                      if self.cf.CFGetTypeID(item) == self.sec.SecIdentityGetTypeID()]
        if len(identities) != 1:
            raise SigningError("Each P12 must contain exactly one signing identity.")
        certificate = self.copied("SecIdentityCopyCertificate", identities[0])
        certificate_data = self.retain_result(self.sec.SecCertificateCopyData(certificate))
        der = C.string_at(self.cf.CFDataGetBytePtr(certificate_data), self.cf.CFDataGetLength(certificate_data))
        key = self.copied("SecIdentityCopyPrivateKey", identities[0])
        self.set_partitions(key, keychain_password)
        return hashlib.sha1(der).hexdigest().upper()

    def set_partitions(self, key, password):
        # This is the native operation used by Apple's security tool. The
        # partition description contains a hex-encoded XML property list.
        # Source: apple-oss-distributions/Security, db15acbe6a7f257a859ad9a3bb86097bfe0679d9,
        # SecurityTool/macOS/keychain_find.c, keychain_set_partition_list.
        access = self.copied("SecKeychainItemCopyAccess", key)
        authorization = C.c_void_p.in_dll(self.sec, "kSecACLAuthorizationPartitionID").value
        acls = self.retain_result(self.sec.SecAccessCopyMatchingACLList(access, authorization))
        entries = self.values(acls)
        if not entries:
            raise SigningError("The imported signing key has no partition ACL.")
        description = self.string(plistlib.dumps({"Partitions": ["apple-tool:", "apple:"]},
                                                 fmt=plistlib.FMT_XML).hex())
        for acl in entries:
            apps, old_description, prompt = C.c_void_p(), C.c_void_p(), C.c_uint32()
            self.check(self.sec.SecACLCopyContents(acl, C.byref(apps), C.byref(old_description), C.byref(prompt)), "read partition ACL")
            if apps.value:
                self.retain_result(apps)
            if old_description.value:
                self.retain_result(old_description)
            self.check(self.sec.SecACLSetContents(acl, apps, description, prompt), "set partition ACL")
        self.check(self.sec.SecKeychainItemSetAccessWithPassword(key, access, len(password), password), "save partition ACL")

    def restore(self, snapshot):
        failures = []
        for operation, value in (("SecKeychainSetSearchList", snapshot[0]),
                                 ("SecKeychainSetDefault", snapshot[1])):
            if getattr(self.sec, operation)(value):
                failures.append(operation)
        if failures:
            raise SigningError("Could not restore the runner keychain configuration.")

    def delete(self, keychain):
        self.check(self.sec.SecKeychainDelete(keychain), "delete temporary keychain")

    def close(self):
        for reference in reversed(self.refs):
            self.cf.CFRelease(reference)
        self.refs.clear()


class Credentials:
    def __init__(self, env, backend=None):
        self.env = dict(env)
        self.backend = backend
        self.root = self.keychain = self.snapshot = None

    def validate(self):
        require_runner(self.env)
        if any(not self.env.get(name) for name in SECRET_NAMES):
            raise SigningError("A required macOS signing secret is missing.")
        for role in ("APPLICATION", "INSTALLER"):
            if not re.fullmatch(r"[0-9A-Fa-f]{40}", self.env.get(f"MACOS_{role}_SHA1", "")):
                raise SigningError("Both approved signing fingerprints must be configured.")
            try:
                payload = base64.b64decode(self.env[f"MACOS_{role}_P12_BASE64"], validate=True)
            except (ValueError, binascii.Error):
                raise SigningError("A signing identity has invalid base64 encoding.") from None
            if not payload or len(payload) > 1024 * 1024:
                raise SigningError("A signing identity has an invalid size.")
        if not re.fullmatch(r"[A-Za-z0-9]{10}", self.env["MACOS_NOTARY_KEY_ID"]):
            raise SigningError("The notarization key identifier is invalid.")
        if not re.fullmatch(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}", self.env["MACOS_NOTARY_ISSUER_ID"]):
            raise SigningError("The notarization issuer identifier is invalid.")
        key = self.env["MACOS_NOTARY_PRIVATE_KEY"].strip()
        if not re.fullmatch(r"-{5}BEGIN PRIVATE KEY-{5}\n[A-Za-z0-9+/=\r\n]+\n-{5}END PRIVATE KEY-{5}", key):
            raise SigningError("The notarization private key must be PKCS8 PEM.")
        temp = Path(self.env.get("RUNNER_TEMP", ""))
        if not temp.is_absolute() or not temp.is_dir():
            raise SigningError("The runner temporary directory is invalid.")

    def __enter__(self):
        self.validate()
        self.backend = self.backend or NativeSecurity()
        try:
            self.root = Path(tempfile.mkdtemp(prefix="vadgr-signing-", dir=self.env["RUNNER_TEMP"]))
            self.root_identity = (self.root.stat().st_dev, self.root.stat().st_ino)
            self.snapshot = self.backend.snapshot()
            path = self.root / "signing.keychain-db"
            password = secrets.token_hex(32).encode()
            self.keychain = self.backend.create(path, password)
            self.backend.restrict_search(self.keychain)
            child = {name: value for name, value in self.env.items() if name not in SECRET_NAMES}
            for role in ("APPLICATION", "INSTALLER"):
                fingerprint = self.backend.import_identity(
                    self.keychain, base64.b64decode(self.env[f"MACOS_{role}_P12_BASE64"], validate=True),
                    self.env[f"MACOS_{role}_P12_PASSWORD"], password)
                if fingerprint != self.env[f"MACOS_{role}_SHA1"].upper():
                    raise SigningError("An imported identity does not match its approved fingerprint.")
                child[f"{role}_IDENTITY"] = fingerprint
            notary = self.root / "notarization.p8"
            descriptor = os.open(notary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(self.env["MACOS_NOTARY_PRIVATE_KEY"])
            child.update(VADGR_MACOS_KEYCHAIN=str(path), VADGR_NOTARY_KEY_FILE=str(notary),
                         VADGR_NOTARY_KEY_ID=self.env["MACOS_NOTARY_KEY_ID"],
                         VADGR_NOTARY_ISSUER_ID=self.env["MACOS_NOTARY_ISSUER_ID"])
            return child
        except BaseException:
            self.cleanup()
            raise

    def cleanup(self):
        failed = False
        for operation in (
            lambda: self.backend.restore(self.snapshot) if self.snapshot is not None else None,
            lambda: self.backend.delete(self.keychain) if self.keychain is not None else None,
            lambda: self.backend.close() if self.backend is not None else None,
        ):
            try:
                operation()
            except Exception:
                failed = True
        if self.root is not None:
            try:
                info = self.root.lstat()
                if self.root.is_symlink() or (info.st_dev, info.st_ino) != self.root_identity:
                    raise SigningError("Temporary credential directory identity changed.")
                shutil.rmtree(self.root)
            except Exception:
                failed = True
        for name in SECRET_NAMES:
            self.env.pop(name, None)
        if failed:
            raise SigningError("Temporary credential cleanup failed; discard this runner.")

    def __exit__(self, *_):
        self.cleanup()


def stop_owned_group(process):
    """Stop only the session created for this signing command, then reap it."""
    # start_new_session makes this child's PID its process group ID. Keep that
    # exact identity; never search for another process by name or command line.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait(timeout=5)
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            process.wait(timeout=5)
            return
        time.sleep(0.05)
    # A shell can exit before its signing descendants. Test the group above,
    # not only the shell's return code, before escalating after the grace period.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def run_command(command, env, backend=None):
    require_runner(env)
    if not command:
        raise SigningError("A signing command is required after --.")
    if any(value and value in argument for name in SECRET_NAMES
           for value in [env.get(name, "")] for argument in command):
        raise SigningError("A credential must not appear in a command argument.")
    with Credentials(env, backend) as child:
        # IDs are metadata, but GitHub receives them as secrets. Mask them before
        # Apple's tools can include either identifier in an error message.
        for name in ("VADGR_NOTARY_KEY_ID", "VADGR_NOTARY_ISSUER_ID"):
            print(f"::add-mask::{child[name]}", flush=True)
        process = subprocess.Popen(command, env=child, start_new_session=True)
        try:
            result = process.wait()
        except BaseException:
            stop_owned_group(process)
            raise
        if result:
            stop_owned_group(process)
        return result


def main():
    def interrupted(_signal, _frame):
        # A repeated cancellation must not interrupt process termination or
        # credential cleanup. The wrapper exits as soon as those steps finish.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise SigningError("Signing was interrupted.")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        if len(sys.argv) < 3 or sys.argv[1] != "--":
            raise SigningError("Usage: macos_signing_credentials.py -- command [arguments]")
        return run_command(sys.argv[2:], os.environ)
    except SigningError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print("macOS credential preparation or signing command failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
