#![cfg(target_os = "windows")]

use serde::Deserialize;
use std::ffi::{OsString, c_void};
use std::os::windows::ffi::OsStringExt;
use std::path::PathBuf;
use std::ptr;
use std::sync::atomic::{AtomicIsize, AtomicPtr, Ordering};
use windows_sys::Win32::System::Com::CoTaskMemFree;
use windows_sys::Win32::UI::Input::KeyboardAndMouse::EnableWindow;
use windows_sys::Win32::UI::Shell::{FOLDERID_LocalAppData, KF_FLAG_DEFAULT, SHGetKnownFolderPath};
use windows_sys::Win32::UI::WindowsAndMessaging::{PostMessageW, SendMessageW, SetWindowTextW};

const S_OK: i32 = 0;
const E_FAIL: i32 = 0x8000_4005_u32 as i32;
const E_INVALIDARG: i32 = 0x8007_0057_u32 as i32;
const BA_FUNCTIONS_MESSAGE_ON_DETECT_COMPLETE: u32 = 65_542;
const BA_FUNCTIONS_API_VERSION: u64 = (2024_u64 << 48) | (1 << 32) | (1 << 16);
const BA_FUNCTIONS_MESSAGE_ON_THEME_LOADED: u32 = 1024;
const BA_FUNCTIONS_MESSAGE_WINDOW_PROC: u32 = 1025;
const BA_FUNCTIONS_MESSAGE_ON_THEME_CONTROL_LOADED: u32 = 1029;
const WM_VADGR_APPLY_ACCEPTANCE: u32 = 0x87f0;
const BM_SETCHECK: u32 = 0x00f1;
const BST_CHECKED: usize = 1;
const MAX_ACCEPTANCE_BYTES: u64 = 64 * 1024;
static CONTEXT: AtomicPtr<Context> = AtomicPtr::new(ptr::null_mut());

#[repr(C)]
pub struct BaFunctionsCreateArgs {
    cb_size: u32,
    api_version: u64,
    bootstrapper_engine: *mut c_void,
    bootstrapper_command: *mut c_void,
}

type BaFunctionsProc =
    unsafe extern "system" fn(u32, *const c_void, *mut c_void, *mut c_void) -> i32;

#[repr(C)]
pub struct BaFunctionsCreateResults {
    cb_size: u32,
    callback: Option<BaFunctionsProc>,
    context: *mut c_void,
}

#[repr(C)]
pub struct BaFunctionsDestroyArgs {
    cb_size: u32,
    reload: i32,
}

#[repr(C)]
pub struct BaFunctionsDestroyResults {
    cb_size: u32,
    disable_unloading: i32,
}

#[repr(C)]
struct ThemeControlLoadedArgs {
    cb_size: u32,
    name: *const u16,
    id: u16,
    window: isize,
}

#[repr(C)]
struct ThemeLoadedArgs {
    cb_size: u32,
    window: isize,
}

#[repr(C)]
struct WindowProcArgs {
    cb_size: u32,
    window: isize,
    message: u32,
    wparam: usize,
    lparam: isize,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TermsAcceptance {
    schema: u32,
    terms_version: String,
    terms_sha256: String,
    accepted_at: String,
    installer_version: String,
    installer_artifact_sha256: String,
    install_scope: String,
    installation_id: String,
    assent_method: String,
}

/// What this machine already says about the terms in this installer.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Acceptance {
    /// Nothing usable is stored, so the reader accepts in this installer.
    Absent,
    /// This machine already accepted exactly these bytes under this version.
    Matches,
    /// This machine accepted this same version with different bytes.
    ///
    /// The recorder refuses that pair on purpose: a version that did not move
    /// while its text did must not pass as accepted. Without this state the
    /// installer asks the reader to accept, works for several minutes, and
    /// then fails in its commit action, which reaches the reader as a generic
    /// installer error code and a full rollback with no reason in it. Saying
    /// so before anything is installed is the whole point of this state.
    VersionConflict,
}

struct Context {
    acceptance: Acceptance,
    parent: AtomicIsize,
    checkbox: AtomicIsize,
    install_button: AtomicIsize,
    subtitle: AtomicIsize,
}

impl Context {
    fn new() -> Self {
        Self {
            acceptance: acceptance_state(),
            parent: AtomicIsize::new(0),
            checkbox: AtomicIsize::new(0),
            install_button: AtomicIsize::new(0),
            subtitle: AtomicIsize::new(0),
        }
    }

    unsafe fn apply(&self) {
        match self.acceptance {
            Acceptance::Absent => {}
            // SAFETY: WiX owns every live theme window for the duration of this
            // callback, which is the only place either of these runs.
            Acceptance::Matches => unsafe { self.apply_previous_acceptance() },
            Acceptance::VersionConflict => unsafe { self.apply_version_conflict() },
        }
    }

    unsafe fn apply_previous_acceptance(&self) {
        let checkbox = self.checkbox.load(Ordering::Acquire);
        if checkbox != 0 {
            let text = wide(&format!(
                "Terms version {} was accepted previously",
                env!("VADGR_TERMS_VERSION")
            ));
            // SAFETY: WiX owns both live theme windows for the duration of this callback.
            unsafe {
                SendMessageW(checkbox as _, BM_SETCHECK, BST_CHECKED, 0);
                SetWindowTextW(checkbox as _, text.as_ptr());
                EnableWindow(checkbox as _, 0);
            }
        }
        let install_button = self.install_button.load(Ordering::Acquire);
        if install_button != 0 {
            // SAFETY: WiX owns the live theme window for the duration of this callback.
            unsafe { EnableWindow(install_button as _, 1) };
        }
    }

    unsafe fn apply_version_conflict(&self) {
        let subtitle = self.subtitle.load(Ordering::Acquire);
        if subtitle != 0 {
            let text = wide(&conflict_message(env!("VADGR_TERMS_VERSION")));
            // SAFETY: WiX owns the live theme window for the duration of this callback.
            unsafe { SetWindowTextW(subtitle as _, text.as_ptr()) };
        }
        // The checkbox is disabled rather than left to the reader, because
        // accepting cannot succeed here and the install action turns itself on
        // when the box is ticked. There is nothing to accept, so nothing to tick.
        let checkbox = self.checkbox.load(Ordering::Acquire);
        if checkbox != 0 {
            // SAFETY: WiX owns the live theme window for the duration of this callback.
            unsafe { EnableWindow(checkbox as _, 0) };
        }
        let install_button = self.install_button.load(Ordering::Acquire);
        if install_button != 0 {
            // SAFETY: WiX owns the live theme window for the duration of this callback.
            unsafe { EnableWindow(install_button as _, 0) };
        }
    }
}

/// The one line the reader sees instead of a bare installer error code.
///
/// It states the product fact and nothing else: which terms version this
/// machine holds, that its text differs from the text in this installer, and
/// that the installation will not go on. It names no file, no path and no
/// internal detail, because this sentence is part of the product.
/// It is also short enough to be read whole. The label that carries it is one
/// line and does not wrap, so a sentence wider than the label loses its end
/// silently. The first version of this message did exactly that: it was 527
/// logical pixels against a 506 pixel label and reached the reader as
/// "so this installer cannot", with the word that mattered cut off.
fn conflict_message(terms_version: &str) -> String {
    format!(
        "Terms version {terms_version} was accepted with different text. \
Installation cannot continue."
    )
}

/// Creates the WiX Standard Bootstrapper Application extension context.
///
/// # Safety
///
/// WiX must pass pointers to structures matching the WiX 7 BAFunctions ABI.
#[unsafe(no_mangle)]
pub unsafe extern "system" fn BAFunctionsCreate(
    args: *const BaFunctionsCreateArgs,
    results: *mut BaFunctionsCreateResults,
) -> i32 {
    if args.is_null() || results.is_null() {
        return E_INVALIDARG;
    }
    // SAFETY: both structures start with cbSize; reject a different ABI before use.
    if unsafe {
        (*args).cb_size as usize != std::mem::size_of::<BaFunctionsCreateArgs>()
            || (*results).cb_size as usize != std::mem::size_of::<BaFunctionsCreateResults>()
    } {
        return E_INVALIDARG;
    }
    // SAFETY: the complete create structure size was checked above.
    if unsafe { (*args).api_version != BA_FUNCTIONS_API_VERSION } {
        return E_INVALIDARG;
    }
    let created = std::panic::catch_unwind(|| Box::new(Context::new()));
    let Ok(context) = created else {
        return E_FAIL;
    };
    let context = Box::into_raw(context);
    if CONTEXT
        .compare_exchange(
            ptr::null_mut(),
            context,
            Ordering::AcqRel,
            Ordering::Acquire,
        )
        .is_err()
    {
        // SAFETY: this allocation was not published because a context already existed.
        unsafe { drop(Box::from_raw(context)) };
        return E_FAIL;
    }
    // SAFETY: WiX supplies writable results with the ABI layout declared by BAFunctions.h.
    unsafe {
        (*results).callback = Some(ba_functions_proc);
        (*results).context = context.cast();
    }
    S_OK
}

/// Releases the extension context before WiX unloads this DLL.
///
/// # Safety
///
/// WiX must pass a writable results structure matching the WiX 7 BAFunctions ABI.
#[unsafe(no_mangle)]
pub unsafe extern "system" fn BAFunctionsDestroy(
    _args: *const BaFunctionsDestroyArgs,
    results: *mut BaFunctionsDestroyResults,
) {
    if !results.is_null() {
        // SAFETY: WiX supplies writable results with the ABI layout declared by BAFunctions.h.
        unsafe { (*results).disable_unloading = 0 };
    }
    let context = CONTEXT.swap(ptr::null_mut(), Ordering::AcqRel);
    if !context.is_null() {
        // SAFETY: BAFunctionsCreate published this allocation exactly once.
        unsafe { drop(Box::from_raw(context)) };
    }
}

unsafe extern "system" fn ba_functions_proc(
    message: u32,
    args: *const c_void,
    _results: *mut c_void,
    context: *mut c_void,
) -> i32 {
    if context.is_null() {
        return E_INVALIDARG;
    }
    let executed = std::panic::catch_unwind(|| {
        // SAFETY: the pointer was created by BAFunctionsCreate and remains owned until destroy.
        let context = unsafe { &*(context.cast::<Context>()) };
        match message {
            BA_FUNCTIONS_MESSAGE_ON_DETECT_COMPLETE => {
                let parent = context.parent.load(Ordering::Acquire);
                if context.acceptance != Acceptance::Absent && parent != 0 {
                    // SAFETY: WiX owns this window until the bundle UI closes.
                    unsafe { PostMessageW(parent as _, WM_VADGR_APPLY_ACCEPTANCE, 0, 0) };
                }
            }
            BA_FUNCTIONS_MESSAGE_ON_THEME_LOADED if !args.is_null() => {
                // SAFETY: this message carries BA_FUNCTIONS_ONTHEMELOADED_ARGS.
                let args = unsafe { &*(args.cast::<ThemeLoadedArgs>()) };
                context.parent.store(args.window, Ordering::Release);
                unsafe { context.apply() };
            }
            BA_FUNCTIONS_MESSAGE_WINDOW_PROC if !args.is_null() => {
                // SAFETY: this message carries BA_FUNCTIONS_WNDPROC_ARGS.
                let args = unsafe { &*(args.cast::<WindowProcArgs>()) };
                if args.message == WM_VADGR_APPLY_ACCEPTANCE {
                    unsafe { context.apply() };
                }
            }
            BA_FUNCTIONS_MESSAGE_ON_THEME_CONTROL_LOADED if !args.is_null() => {
                // SAFETY: this message carries BA_FUNCTIONS_ONTHEMECONTROLLOADED_ARGS.
                let args = unsafe { &*(args.cast::<ThemeControlLoadedArgs>()) };
                if let Some(name) = unsafe { wide_ptr_to_string(args.name) } {
                    match name.as_str() {
                        "EulaAcceptCheckbox" => {
                            context.checkbox.store(args.window, Ordering::Release)
                        }
                        "InstallButton" => {
                            context.install_button.store(args.window, Ordering::Release)
                        }
                        "TermsSubtitle" => context.subtitle.store(args.window, Ordering::Release),
                        _ => {}
                    }
                    unsafe { context.apply() };
                }
            }
            _ => {}
        }
    });
    if executed.is_ok() { S_OK } else { E_FAIL }
}

fn acceptance_state() -> Acceptance {
    let Some(path) = acceptance_path() else {
        return Acceptance::Absent;
    };
    acceptance_state_at(
        &path,
        env!("VADGR_TERMS_VERSION"),
        env!("VADGR_TERMS_SHA256"),
    )
}

fn acceptance_state_at(
    path: &std::path::Path,
    terms_version: &str,
    terms_sha256: &str,
) -> Acceptance {
    let Ok(metadata) = std::fs::metadata(path) else {
        return Acceptance::Absent;
    };
    if !metadata.is_file() || metadata.len() > MAX_ACCEPTANCE_BYTES {
        return Acceptance::Absent;
    }
    let Ok(bytes) = std::fs::read(path) else {
        return Acceptance::Absent;
    };
    let Ok(record) = serde_json::from_slice::<TermsAcceptance>(&bytes) else {
        return Acceptance::Absent;
    };
    // Two different questions, so two different tests.
    //
    // Whether the recorder will refuse is the only thing that decides a
    // conflict, so this mirrors exactly what the recorder reads: the schema,
    // both digests and the scope. Adding conditions the recorder does not
    // share would leave a record that this page waves through and the recorder
    // then rejects, which is the failure this state exists to prevent.
    let readable_by_the_recorder = record.schema == 1
        && valid_sha256(&record.terms_sha256)
        && valid_sha256(&record.installer_artifact_sha256)
        && record.install_scope == "user";
    if !readable_by_the_recorder || record.terms_version != terms_version {
        return Acceptance::Absent;
    }
    if !record.terms_sha256.eq_ignore_ascii_case(terms_sha256) {
        return Acceptance::VersionConflict;
    }
    // Treating something as already accepted is the generous answer, so it
    // takes the strict test. Anything short of a complete record asks the
    // reader again rather than deciding on their behalf.
    let complete = record.assent_method == "unchecked_checkbox_then_install"
        && !record.accepted_at.trim().is_empty()
        && !record.installer_version.trim().is_empty()
        && !record.installation_id.trim().is_empty();
    if complete {
        Acceptance::Matches
    } else {
        Acceptance::Absent
    }
}

fn acceptance_path() -> Option<PathBuf> {
    let mut raw = ptr::null_mut();
    // SAFETY: SHGetKnownFolderPath initializes raw on success; the returned allocation is freed below.
    if unsafe {
        SHGetKnownFolderPath(
            &FOLDERID_LocalAppData,
            KF_FLAG_DEFAULT as u32,
            ptr::null_mut(),
            &mut raw,
        )
    } < 0
        || raw.is_null()
    {
        return None;
    }
    let mut length = 0;
    // SAFETY: the successful API call returned a NUL-terminated UTF-16 string.
    unsafe {
        while *raw.add(length) != 0 {
            length += 1;
        }
    }
    // SAFETY: the allocation contains at least length initialized UTF-16 code units.
    let local = OsString::from_wide(unsafe { std::slice::from_raw_parts(raw, length) });
    // SAFETY: SHGetKnownFolderPath allocates with the COM task allocator.
    unsafe { CoTaskMemFree(raw.cast()) };
    Some(
        PathBuf::from(local)
            .join("vadgr")
            .join("terms-acceptance.json"),
    )
}

unsafe fn wide_ptr_to_string(value: *const u16) -> Option<String> {
    if value.is_null() {
        return None;
    }
    let mut length = 0;
    // SAFETY: WiX supplies a NUL-terminated control name. The cap rejects malformed input.
    unsafe {
        while length < 128 && *value.add(length) != 0 {
            length += 1;
        }
    }
    if length == 128 {
        return None;
    }
    // SAFETY: the preceding bounded scan found the end of this UTF-16 string.
    String::from_utf16(unsafe { std::slice::from_raw_parts(value, length) }).ok()
}

fn wide(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(std::iter::once(0)).collect()
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64 && value.chars().all(|character| character.is_ascii_hexdigit())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn create_rejects_the_previous_abi_before_touching_results() {
        let mut args = BaFunctionsCreateArgs {
            cb_size: 24,
            api_version: BA_FUNCTIONS_API_VERSION,
            bootstrapper_engine: ptr::null_mut(),
            bootstrapper_command: ptr::null_mut(),
        };
        let mut results = BaFunctionsCreateResults {
            cb_size: std::mem::size_of::<BaFunctionsCreateResults>() as u32,
            callback: None,
            context: ptr::null_mut(),
        };
        // SAFETY: test-owned complete structures remain live through these calls.
        assert_eq!(
            unsafe { BAFunctionsCreate(&args, &mut results) },
            E_INVALIDARG
        );
        args.cb_size = std::mem::size_of::<BaFunctionsCreateArgs>() as u32;
        args.api_version = 0;
        assert_eq!(
            unsafe { BAFunctionsCreate(&args, &mut results) },
            E_INVALIDARG
        );
        assert!(results.callback.is_none());
        assert!(results.context.is_null());
        assert_eq!(BA_FUNCTIONS_MESSAGE_ON_DETECT_COMPLETE, 65_542);
    }

    #[test]
    fn digest_shape_is_closed() {
        assert!(valid_sha256(&"a".repeat(64)));
        assert!(!valid_sha256(&"a".repeat(63)));
        assert!(!valid_sha256(&format!("{}g", "a".repeat(63))));
    }

    #[test]
    fn acceptance_requires_the_exact_version_and_checksum() {
        let path = std::env::temp_dir().join(format!(
            "vadgr-ba-acceptance-{}-{}.json",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let hash = "a".repeat(64);
        let record = json!({
            "schema": 1,
            "terms_version": "1.0",
            "terms_sha256": hash,
            "accepted_at": "2026-09-02T00:00:00Z",
            "installer_version": "0.5.0",
            "installer_artifact_sha256": "b".repeat(64),
            "install_scope": "user",
            "installation_id": "development-test",
            "assent_method": "unchecked_checkbox_then_install"
        });
        std::fs::write(&path, serde_json::to_vec(&record).unwrap()).unwrap();

        assert_eq!(
            acceptance_state_at(&path, "1.0", &hash),
            Acceptance::Matches
        );
        // Another version is simply not this installer's question.
        assert_eq!(acceptance_state_at(&path, "2.0", &hash), Acceptance::Absent);
        // The same version with different text is the condition the recorder
        // refuses. Before this was its own state, the installer asked the
        // reader to accept and then failed in its commit action.
        assert_eq!(
            acceptance_state_at(&path, "1.0", &"c".repeat(64)),
            Acceptance::VersionConflict
        );
        std::fs::write(&path, b"not json").unwrap();
        assert_eq!(acceptance_state_at(&path, "1.0", &hash), Acceptance::Absent);

        std::fs::remove_file(path).unwrap();
    }

    /// A record whose version matches and whose text differs is a conflict
    /// even when it is incomplete in ways the recorder does not read.
    ///
    /// The recorder refuses on the schema, the two digests, the scope, the
    /// version and the text. Demanding more here than the recorder demands
    /// would wave an install through that the recorder then rejects, which is
    /// exactly the blind failure this state exists to prevent.
    #[test]
    fn a_conflict_is_decided_on_what_the_recorder_reads() {
        let hash = "a".repeat(64);
        for (field, value) in [
            ("assent_method", json!("assumed")),
            ("installation_id", json!("")),
            ("accepted_at", json!("   ")),
            ("installer_version", json!("")),
        ] {
            let path = std::env::temp_dir().join(format!(
                "vadgr-ba-partial-{}-{}-{field}.json",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
            let mut record = json!({
                "schema": 1,
                "terms_version": "1.0",
                "terms_sha256": hash,
                "accepted_at": "2026-09-02T00:00:00Z",
                "installer_version": "0.5.0",
                "installer_artifact_sha256": "b".repeat(64),
                "install_scope": "user",
                "installation_id": "development-test",
                "assent_method": "unchecked_checkbox_then_install"
            });
            record[field] = value;
            std::fs::write(&path, serde_json::to_vec(&record).unwrap()).unwrap();
            assert_eq!(
                acceptance_state_at(&path, "1.0", &"c".repeat(64)),
                Acceptance::VersionConflict,
                "{field}"
            );
            // The same record is not treated as already accepted, because
            // accepting on the reader's behalf takes the strict test.
            assert_eq!(
                acceptance_state_at(&path, "1.0", &hash),
                Acceptance::Absent,
                "{field}"
            );
            std::fs::remove_file(path).unwrap();
        }
    }

    #[test]
    fn a_record_the_recorder_cannot_read_is_absent() {
        let hash = "a".repeat(64);
        for (field, value) in [
            ("schema", json!(2)),
            ("install_scope", json!("machine")),
            ("installer_artifact_sha256", json!("short")),
            ("terms_sha256", json!("short")),
        ] {
            let path = std::env::temp_dir().join(format!(
                "vadgr-ba-unsound-{}-{}-{field}.json",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
            let mut record = json!({
                "schema": 1,
                "terms_version": "1.0",
                "terms_sha256": hash,
                "accepted_at": "2026-09-02T00:00:00Z",
                "installer_version": "0.5.0",
                "installer_artifact_sha256": "b".repeat(64),
                "install_scope": "user",
                "installation_id": "development-test",
                "assent_method": "unchecked_checkbox_then_install"
            });
            record[field] = value;
            std::fs::write(&path, serde_json::to_vec(&record).unwrap()).unwrap();
            // The recorder cannot read this record at all, so it will not get
            // as far as comparing the text. Reporting a conflict here would
            // name the wrong reason for the failure that follows.
            assert_eq!(
                acceptance_state_at(&path, "1.0", &"c".repeat(64)),
                Acceptance::Absent,
                "{field}"
            );
            std::fs::remove_file(path).unwrap();
        }
    }

    #[test]
    fn the_conflict_message_is_one_product_fact_and_names_nothing_internal() {
        let message = conflict_message("1.0");
        assert!(message.contains("Terms version 1.0"));
        assert!(message.contains("different text"));
        assert!(message.contains("cannot continue"));
        // Public installer text states the product fact only.
        for forbidden in [
            "terms-acceptance",
            ".json",
            "sha256",
            "C:\\",
            "AppData",
            "MSI",
            "1722",
        ] {
            assert!(!message.contains(forbidden), "{forbidden} is internal");
        }
        // One line, and short enough for the label that carries it.
        assert!(!message.contains('\n') && message.len() <= 120, "{message}");
    }

    /// The label is one line and does not wrap, so a message wider than it
    /// loses its end with no sign that anything is missing. This computes the
    /// label from the theme's own numbers rather than trusting a guess, which
    /// is how the first version of the message shipped clipped.
    #[test]
    fn the_message_fits_the_label_that_carries_it() {
        let theme = include_str!("../../VadgrTheme.xml");
        let number = |source: &str, key: &str| -> i32 {
            let start = source.find(key).expect("the theme names this attribute") + key.len();
            let rest = &source[start..];
            let end = rest.find('"').expect("a closed attribute");
            rest[..end].parse().expect("a whole number")
        };
        let window = number(theme, "<Window Width=\"");
        let label = &theme[theme.find("Name=\"TermsSubtitle\"").expect("the label")..];
        let left = number(label, " X=\"");
        // A negative width in this theme means a gap from the right edge.
        let gap = -number(label, " Width=\"");
        let available = window - left - gap;
        assert!(available > 0, "the label has no width: {available}");

        // Measured on this product with the theme's own font, Segoe UI at the
        // small size: the widest of several candidate sentences averaged 5.25
        // logical pixels per character. The bound is deliberately above that,
        // because a font that renders a little wider must still fit.
        const WIDEST_AVERAGE_ADVANCE: i32 = 56;
        for version in ["1.0", "10.25"] {
            let message = conflict_message(version);
            let needed = message.len() as i32 * WIDEST_AVERAGE_ADVANCE / 10;
            assert!(
                needed <= available,
                "{message:?} needs about {needed} of {available} logical pixels"
            );
        }
    }

    #[test]
    fn the_theme_names_the_label_that_carries_the_reason() {
        // The bootstrapper reaches a control by name, so an unnamed label
        // cannot be written to and the reason would have nowhere to go.
        let theme = include_str!("../../VadgrTheme.xml");
        assert!(theme.contains("Name=\"TermsSubtitle\""));
        assert!(theme.contains("Name=\"EulaAcceptCheckbox\""));
        assert!(theme.contains("Name=\"InstallButton\""));
    }
}
