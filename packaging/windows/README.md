# Windows package inputs

These WiX v4 projects build the current-user MSI and Burn setup selected for
Vadgr 0.5.0. The MSI is fixed to the current user and does not offer a
machine-wide choice. The deterministic payload generator gives every private
payload file a stable UUIDv5 component identity and HKCU key path, and gives
every payload directory an uninstall row before Windows Installer validation.
The payload directory must
be a clean release staging directory. It must
contain `vadgr.exe`, `vadgr-app.exe`, `install-receipt.json`, the private CUA
runtime, and the complete generated offline legal and notice payload.

The bundle build also requires the reviewed canonical terms as RTF through the
`TermsRtf` build property. A missing terms file, payload directory, MSI path, or
version is a build failure. The custom Burn theme follows the approved Vadgr
terms, progress, success, and rollback hierarchy. Do not substitute draft or
placeholder terms.

The output of these projects is unsigned. Release automation must sign and
verify every installed PE and DLL, the MSI, the detached Burn engine, and the
final setup in the required order. An unsigned build is for development only.
