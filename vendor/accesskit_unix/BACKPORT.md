# AccessKit Unix 0.21.1 backport

This is the crates.io source for `accesskit_unix` 0.21.1. Vadgr changes one
line in `src/context.rs` to watch the AT-SPI `IsEnabled` property instead of
`ScreenReaderEnabled`.

The correction is upstream AccessKit commit
`e7299a753d78e8b00dd75e1d2182abb517648f98`, released in
`accesskit_unix` 0.22.0. The current eframe dependency requires the 0.21
series. This local backport keeps the compatible API while allowing ordinary
AT-SPI clients, not only screen readers, to activate the application tree.
