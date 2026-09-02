# macOS package

`build.sh` assembles the unsigned architecture-specific app. It includes the
single Vadgr backend/console executable and the separately signed
`Vadgr Computer Use.app` responsible-process host. CUA always starts below that
host, so Accessibility and Screen Recording attach to the stable
`com.montbrain.vadgr.cua` designated requirement across updates.

The protected release job signs nested code inside-out, signs the outer app,
builds and signs the product package, notarizes the exact package, staples it,
and verifies every layer. This source provides no ad hoc or self-signed path.
