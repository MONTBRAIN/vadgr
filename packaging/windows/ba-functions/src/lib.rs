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
const BA_FUNCTIONS_MESSAGE_ON_DETECT_COMPLETE: u32 = 1;
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
    bootstrapper_create_args: *mut c_void,
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

struct Context {
    accepted: bool,
    parent: AtomicIsize,
    checkbox: AtomicIsize,
    install_button: AtomicIsize,
}

impl Context {
    fn new() -> Self {
        Self {
            accepted: acceptance_matches(),
            parent: AtomicIsize::new(0),
            checkbox: AtomicIsize::new(0),
            install_button: AtomicIsize::new(0),
        }
    }

    unsafe fn apply(&self) {
        if !self.accepted {
            return;
        }
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
}

/// Creates the WiX Standard Bootstrapper Application extension context.
///
/// # Safety
///
/// WiX must pass pointers to structures matching the WiX 4.0 BAFunctions ABI.
#[unsafe(no_mangle)]
pub unsafe extern "system" fn BAFunctionsCreate(
    args: *const BaFunctionsCreateArgs,
    results: *mut BaFunctionsCreateResults,
) -> i32 {
    if args.is_null() || results.is_null() {
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
/// WiX must pass a writable results structure matching the WiX 4.0 BAFunctions ABI.
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
                if context.accepted && parent != 0 {
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

fn acceptance_matches() -> bool {
    let Some(path) = acceptance_path() else {
        return false;
    };
    acceptance_matches_at(
        &path,
        env!("VADGR_TERMS_VERSION"),
        env!("VADGR_TERMS_SHA256"),
    )
}

fn acceptance_matches_at(path: &std::path::Path, terms_version: &str, terms_sha256: &str) -> bool {
    let Ok(metadata) = std::fs::metadata(path) else {
        return false;
    };
    if !metadata.is_file() || metadata.len() > MAX_ACCEPTANCE_BYTES {
        return false;
    }
    let Ok(bytes) = std::fs::read(path) else {
        return false;
    };
    let Ok(record) = serde_json::from_slice::<TermsAcceptance>(&bytes) else {
        return false;
    };
    record.schema == 1
        && record.install_scope == "user"
        && record.assent_method == "unchecked_checkbox_then_install"
        && record.terms_version == terms_version
        && record.terms_sha256.eq_ignore_ascii_case(terms_sha256)
        && valid_sha256(&record.terms_sha256)
        && valid_sha256(&record.installer_artifact_sha256)
        && !record.accepted_at.trim().is_empty()
        && !record.installer_version.trim().is_empty()
        && !record.installation_id.trim().is_empty()
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

        assert!(acceptance_matches_at(&path, "1.0", &hash));
        assert!(!acceptance_matches_at(&path, "2.0", &hash));
        assert!(!acceptance_matches_at(&path, "1.0", &"c".repeat(64)));
        std::fs::write(&path, b"not json").unwrap();
        assert!(!acceptance_matches_at(&path, "1.0", &hash));

        std::fs::remove_file(path).unwrap();
    }
}
