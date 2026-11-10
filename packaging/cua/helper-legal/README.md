# CUA 0.7.9 helper redistribution review

These records authorize only the exact Windows helper inputs identified by the
retained review-input receipts. They do not approve the Vadgr installer, its
terms, its complete dependency inventory, or a final package. The package
approval can therefore bind the later CUA catalog without a circular hash.

The publisher authorized completion, merge and release of CUA 0.7.9 on
2026-09-27 after reviewing its final code. The records cover the exact
predecessor and replacement source revisions required by the signed transition.
Each record identifies one retained review-input receipt and one source
revision. These records implement the publisher decision; they do not assert
review by independent legal counsel.

## Recorded license treatment

- CUA source remains Apache-2.0. Its exact LICENSE and NOTICE travel in the
  broker. The Go runtime and its selected vendored package keep the supplied
  BSD-3-Clause notices and PATENTS files.
- CPython 3.12.14 keeps the complete supplied PYTHON-LICENSE.txt, including
  historical licenses and the Windows redistribution conditions. The selected
  runtime members are matched to the pinned Python archive by their hashes.
- The selected OpenSSL 3.5.8 DLLs remain Apache-2.0. libffi keeps its MIT grant.
  Statically incorporated bzip2, Expat, liblzma, mpdecimal and zlib keep the
  exact supplied notices. These grants permit binary distribution with their
  stated notice conditions; they do not require a recipient source offer for
  these unmodified inputs.
- The unmodified PyInstaller 6.22.2 bootloader is embedded in the combined CUA
  broker. Its explicit bootloader exception permits distributing that combined
  executable. The exception does not authorize distributing a modified
  standalone PyInstaller tool under a different license. The complete COPYING
  file remains in the broker, including its Apache-licensed runtime-hook terms.
- Microsoft VC runtime DLLs remain byte-identical. Preserve their signatures,
  copyright and other notices. They execute only on Windows, including the
  Windows side of WSL. The supplied Python license states the applicable
  redistribution conditions. No Microsoft endorsement or rights in unrelated
  Microsoft products are claimed.

## Permitted transformation

Publisher signing may change only the PE checksum, certificate directory and
appended Authenticode certificate data. Executable sections, resources,
copyright notices and existing upstream signatures must remain unchanged.
Microsoft-signed VC runtime DLLs are vendor-preserve inputs and must never be
publisher-signed. Non-native files are data and must remain byte-identical.

The final distribution must retain all existing license and notice members.
The broker combines unmodified dependency binaries with CUA code using
PyInstaller; packaging normalizes archive metadata, and the publisher adds
Authenticode signatures to unsigned PE members. No dependency source changes
are authorized by this record. The final release records those packaging and
signature changes and identifies the publisher separately from upstream
authors.

## Research checked on 2026-09-26

The exact retained license bytes are the primary record. These upstream sources
confirm their interpretation and scope:

- [Python 3.12.14 Windows redistribution conditions](https://github.com/python/cpython/blob/v3.12.14/PC/crtlicense.txt).
- [PyInstaller 6.22.2 license and bootloader exception](https://github.com/pyinstaller/pyinstaller/blob/v6.22.2/COPYING.txt).
- [Microsoft Visual C++ redistribution guidance](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files).

The native signature reports still have to verify the exact vendor certificate,
chain, timestamp and file digest. This legal record cannot substitute for that
verification or authorize a changed input.
