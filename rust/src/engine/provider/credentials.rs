use crate::engine::types::ProviderError;
use rand::RngExt;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

const RECORD_VERSION: u32 = 1;
const MAX_RECORD_BYTES: u64 = 64 * 1024;
const REFERENCE_PREFIX: &str = "cred_v1_";
const STAGED_PREFIX: &str = ".cred_stage_";

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Credential {
    ApiKey {
        version: u32,
        provider: String,
        api_key: String,
    },
    Oauth {
        version: u32,
        provider: String,
        access_token: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        refresh_token: Option<String>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        expires_at: Option<String>,
    },
}

impl Credential {
    pub fn api_key(provider: impl Into<String>, api_key: impl Into<String>) -> Self {
        Self::ApiKey {
            version: RECORD_VERSION,
            provider: provider.into(),
            api_key: api_key.into(),
        }
    }

    pub fn oauth(
        provider: impl Into<String>,
        access_token: impl Into<String>,
        refresh_token: Option<String>,
        expires_at: Option<String>,
    ) -> Self {
        Self::Oauth {
            version: RECORD_VERSION,
            provider: provider.into(),
            access_token: access_token.into(),
            refresh_token,
            expires_at,
        }
    }

    pub fn provider(&self) -> &str {
        match self {
            Self::ApiKey { provider, .. } | Self::Oauth { provider, .. } => provider,
        }
    }

    pub fn auth_method(&self) -> &'static str {
        match self {
            Self::ApiKey { .. } => "api_key",
            Self::Oauth { .. } => "oauth",
        }
    }

    pub fn secret(&self) -> &str {
        match self {
            Self::ApiKey { api_key, .. } => api_key,
            Self::Oauth { access_token, .. } => access_token,
        }
    }

    pub fn expires_at(&self) -> Option<&str> {
        match self {
            Self::ApiKey { .. } => None,
            Self::Oauth { expires_at, .. } => expires_at.as_deref(),
        }
    }

    fn validate(&self, expected_provider: &str) -> Result<(), ProviderError> {
        let version = match self {
            Self::ApiKey { version, .. } | Self::Oauth { version, .. } => *version,
        };
        if version != RECORD_VERSION {
            return Err(store_error(format!(
                "unsupported credential record version {version}"
            )));
        }
        if self.provider() != expected_provider {
            return Err(store_error(
                "credential provider does not match its connection",
            ));
        }
        if self.secret().trim().is_empty() {
            return Err(store_error("credential secret is empty"));
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub struct CredentialStore {
    directory: PathBuf,
}

impl CredentialStore {
    pub fn native(state_home: Option<PathBuf>) -> Result<Self, ProviderError> {
        let root = match state_home {
            Some(path) if path.is_absolute() => path,
            Some(_) => return Err(store_error("VADGR_STATE_HOME must be an absolute path")),
            None => default_state_root()?,
        };
        Self::new(root.join("credentials"))
    }

    pub fn new(directory: PathBuf) -> Result<Self, ProviderError> {
        let store = Self { directory };
        store.ensure_directory()?;
        Ok(store)
    }

    pub fn directory(&self) -> &Path {
        &self.directory
    }

    pub fn write(&self, credential: &Credential) -> Result<String, ProviderError> {
        credential.validate(credential.provider())?;
        self.ensure_directory()?;
        let bytes = serde_json::to_vec(credential).map_err(store_error)?;
        if bytes.len() as u64 > MAX_RECORD_BYTES {
            return Err(store_error("credential record exceeds 64 KiB"));
        }

        for _ in 0..8 {
            let suffix = random_hex(16);
            let reference = format!("{REFERENCE_PREFIX}{suffix}.json");
            let final_path = self.directory.join(&reference);
            let staged_path = self.directory.join(format!("{STAGED_PREFIX}{suffix}.tmp"));
            let mut file = match create_secret_file(&staged_path) {
                Ok(file) => file,
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(store_error(error)),
            };
            let mut published = false;
            if let Err(error) = (|| -> std::io::Result<()> {
                file.write_all(&bytes)?;
                file.sync_all()?;
                validate_secret_file(&staged_path)?;
                publish_secret_file(&staged_path, &final_path)?;
                published = true;
                sync_directory(&self.directory)?;
                validate_secret_file(&final_path)
            })() {
                let _ = std::fs::remove_file(&staged_path);
                if published {
                    let _ = std::fs::remove_file(&final_path);
                }
                if !published && error.kind() == std::io::ErrorKind::AlreadyExists {
                    continue;
                }
                return Err(store_error(error));
            }
            return Ok(reference);
        }
        Err(store_error(
            "could not allocate a unique credential reference",
        ))
    }

    pub fn read(
        &self,
        reference: &str,
        expected_provider: &str,
    ) -> Result<Credential, ProviderError> {
        validate_reference(reference)?;
        let path = self.directory.join(reference);
        validate_secret_file(&path).map_err(store_error)?;
        let file = OpenOptions::new()
            .read(true)
            .open(&path)
            .map_err(store_error)?;
        let length = file.metadata().map_err(store_error)?.len();
        if length > MAX_RECORD_BYTES {
            return Err(store_error("credential record exceeds 64 KiB"));
        }
        let mut bytes = Vec::with_capacity(length as usize);
        file.take(MAX_RECORD_BYTES + 1)
            .read_to_end(&mut bytes)
            .map_err(store_error)?;
        if bytes.len() as u64 > MAX_RECORD_BYTES {
            return Err(store_error("credential record exceeds 64 KiB"));
        }
        let credential: Credential = serde_json::from_slice(&bytes).map_err(store_error)?;
        credential.validate(expected_provider)?;
        Ok(credential)
    }

    pub fn delete(&self, reference: &str) -> Result<(), ProviderError> {
        validate_reference(reference)?;
        let path = self.directory.join(reference);
        match std::fs::remove_file(path) {
            Ok(()) => {
                sync_directory(&self.directory).map_err(store_error)?;
                Ok(())
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(store_error(error)),
        }
    }

    pub fn cleanup_unreferenced(&self, referenced: &HashSet<String>) -> Result<(), ProviderError> {
        self.ensure_directory()?;
        for entry in std::fs::read_dir(&self.directory).map_err(store_error)? {
            let entry = entry.map_err(store_error)?;
            let name = entry.file_name();
            let Some(name) = name.to_str() else { continue };
            let staged = name.starts_with(STAGED_PREFIX) && name.ends_with(".tmp");
            let orphan = name.starts_with(REFERENCE_PREFIX)
                && name.ends_with(".json")
                && !referenced.contains(name);
            if staged || orphan {
                let metadata = std::fs::symlink_metadata(entry.path()).map_err(store_error)?;
                if metadata.file_type().is_symlink() || !metadata.is_file() {
                    return Err(store_error("credential directory contains an unsafe entry"));
                }
                std::fs::remove_file(entry.path()).map_err(store_error)?;
            }
        }
        sync_directory(&self.directory).map_err(store_error)
    }

    fn ensure_directory(&self) -> Result<(), ProviderError> {
        if let Ok(metadata) = std::fs::symlink_metadata(&self.directory) {
            if metadata.file_type().is_symlink() || !metadata.is_dir() {
                return Err(store_error(
                    "credential directory is not a regular directory",
                ));
            }
        } else {
            create_secret_directory(&self.directory).map_err(store_error)?;
        }
        validate_secret_directory(&self.directory).map_err(store_error)
    }
}

pub fn default_state_root() -> Result<PathBuf, ProviderError> {
    let project = directories::ProjectDirs::from("", "", "vadgr")
        .ok_or_else(|| store_error("the platform local-state directory is unavailable"))?;
    Ok(project
        .state_dir()
        .unwrap_or_else(|| project.data_local_dir())
        .to_path_buf())
}

fn validate_reference(reference: &str) -> Result<(), ProviderError> {
    let Some(suffix) = reference
        .strip_prefix(REFERENCE_PREFIX)
        .and_then(|value| value.strip_suffix(".json"))
    else {
        return Err(store_error("credential reference is malformed"));
    };
    if suffix.len() != 32 || !suffix.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(store_error("credential reference is malformed"));
    }
    Ok(())
}

fn random_hex(bytes: usize) -> String {
    let mut rng = rand::rng();
    (0..bytes)
        .map(|_| format!("{:02x}", rng.random::<u8>()))
        .collect()
}

fn store_error(error: impl std::fmt::Display) -> ProviderError {
    ProviderError::CredentialStore(error.to_string())
}

#[cfg(unix)]
fn create_secret_directory(path: &Path) -> std::io::Result<()> {
    use std::os::unix::fs::{DirBuilderExt, PermissionsExt};

    std::fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(path)?;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700))
}

#[cfg(all(not(unix), not(windows)))]
fn create_secret_directory(path: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(path)
}

#[cfg(windows)]
fn create_secret_directory(path: &Path) -> std::io::Result<()> {
    windows_security::create_directory(path)
}

#[cfg(unix)]
fn create_secret_file(path: &Path) -> std::io::Result<File> {
    use std::os::unix::fs::OpenOptionsExt;

    OpenOptions::new()
        .read(true)
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)
}

#[cfg(all(not(unix), not(windows)))]
fn create_secret_file(path: &Path) -> std::io::Result<File> {
    OpenOptions::new()
        .read(true)
        .write(true)
        .create_new(true)
        .open(path)
}

#[cfg(windows)]
fn create_secret_file(path: &Path) -> std::io::Result<File> {
    windows_security::create_file(path)
}

#[cfg(unix)]
fn validate_secret_directory(path: &Path) -> std::io::Result<()> {
    validate_unix_node(path, true, 0o700)
}

#[cfg(all(not(unix), not(windows)))]
fn validate_secret_directory(path: &Path) -> std::io::Result<()> {
    let metadata = std::fs::symlink_metadata(path)?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(std::io::Error::other("credential directory is unsafe"));
    }
    Ok(())
}

#[cfg(windows)]
fn validate_secret_directory(path: &Path) -> std::io::Result<()> {
    windows_security::validate(path, true)
}

#[cfg(unix)]
fn validate_secret_file(path: &Path) -> std::io::Result<()> {
    validate_unix_node(path, false, 0o600)
}

#[cfg(all(not(unix), not(windows)))]
fn validate_secret_file(path: &Path) -> std::io::Result<()> {
    let metadata = std::fs::symlink_metadata(path)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(std::io::Error::other("credential file is unsafe"));
    }
    Ok(())
}

#[cfg(windows)]
fn validate_secret_file(path: &Path) -> std::io::Result<()> {
    windows_security::validate(path, false)
}

#[cfg(unix)]
fn validate_unix_node(path: &Path, directory: bool, required_mode: u32) -> std::io::Result<()> {
    use std::os::unix::fs::MetadataExt;

    let metadata = std::fs::symlink_metadata(path)?;
    if metadata.file_type().is_symlink()
        || (directory && !metadata.is_dir())
        || (!directory && !metadata.is_file())
    {
        return Err(std::io::Error::other("credential path has an unsafe type"));
    }
    if metadata.uid() != rustix::process::getuid().as_raw() {
        return Err(std::io::Error::other("credential path has the wrong owner"));
    }
    if metadata.mode() & 0o777 != required_mode {
        return Err(std::io::Error::other(format!(
            "credential path mode must be {required_mode:o}"
        )));
    }
    reject_access_acl(path)
}

#[cfg(any(target_os = "linux", target_os = "android"))]
fn reject_access_acl(path: &Path) -> std::io::Result<()> {
    let mut value = vec![0u8; 4096];
    match rustix::fs::lgetxattr(path, "system.posix_acl_access", &mut value) {
        Ok(length) if length > 0 => Err(std::io::Error::other(
            "credential path has an extended access ACL",
        )),
        Ok(_) => Ok(()),
        Err(rustix::io::Errno::NODATA | rustix::io::Errno::NOTSUP) => Ok(()),
        Err(error) => Err(std::io::Error::from_raw_os_error(error.raw_os_error())),
    }
}

#[cfg(target_os = "macos")]
fn reject_access_acl(path: &Path) -> std::io::Result<()> {
    use std::ffi::{CString, c_int, c_void};
    use std::os::unix::ffi::OsStrExt;

    const ACL_TYPE_EXTENDED: c_int = 0x0000_0100;
    const ACL_FIRST_ENTRY: c_int = 0;

    unsafe extern "C" {
        fn acl_get_link_np(path: *const i8, acl_type: c_int) -> *mut c_void;
        fn acl_get_entry(acl: *mut c_void, entry_id: c_int, entry: *mut *mut c_void) -> c_int;
        fn acl_free(value: *mut c_void) -> c_int;
    }

    let path = CString::new(path.as_os_str().as_bytes())
        .map_err(|_| std::io::Error::other("credential path contains a NUL byte"))?;
    // This variant does not follow a final symlink. The type check has already
    // rejected one, but keeping both operations no-follow closes that gap.
    let acl = unsafe { acl_get_link_np(path.as_ptr(), ACL_TYPE_EXTENDED) };
    if acl.is_null() {
        return Err(std::io::Error::last_os_error());
    }
    let mut entry = std::ptr::null_mut();
    let result = unsafe { acl_get_entry(acl, ACL_FIRST_ENTRY, &mut entry) };
    let entry_error = std::io::Error::last_os_error();
    let free_result = unsafe { acl_free(acl) };
    if free_result != 0 {
        return Err(std::io::Error::last_os_error());
    }
    if result == 0 {
        return Err(std::io::Error::other(
            "credential path has an extended access ACL",
        ));
    }
    // Darwin reports EINVAL when an otherwise valid extended ACL has no first
    // entry. Any other error means access could not be proved owner-only.
    if entry_error.raw_os_error() == Some(22) {
        Ok(())
    } else {
        Err(entry_error)
    }
}

#[cfg(all(
    unix,
    not(any(target_os = "linux", target_os = "android", target_os = "macos"))
))]
fn reject_access_acl(_path: &Path) -> std::io::Result<()> {
    Ok(())
}

#[cfg(unix)]
fn sync_directory(path: &Path) -> std::io::Result<()> {
    File::open(path)?.sync_all()
}

#[cfg(not(unix))]
fn sync_directory(_path: &Path) -> std::io::Result<()> {
    Ok(())
}

#[cfg(any(target_os = "linux", target_os = "android", target_os = "macos"))]
fn publish_secret_file(staged: &Path, final_path: &Path) -> std::io::Result<()> {
    rustix::fs::renameat_with(
        rustix::fs::CWD,
        staged,
        rustix::fs::CWD,
        final_path,
        rustix::fs::RenameFlags::NOREPLACE,
    )
    .map_err(|error| std::io::Error::from_raw_os_error(error.raw_os_error()))
}

#[cfg(all(
    unix,
    not(any(target_os = "linux", target_os = "android", target_os = "macos"))
))]
fn publish_secret_file(staged: &Path, final_path: &Path) -> std::io::Result<()> {
    std::fs::hard_link(staged, final_path)?;
    std::fs::remove_file(staged)
}

#[cfg(windows)]
fn publish_secret_file(staged: &Path, final_path: &Path) -> std::io::Result<()> {
    windows_security::publish(staged, final_path)
}

#[cfg(all(not(unix), not(windows)))]
fn publish_secret_file(staged: &Path, final_path: &Path) -> std::io::Result<()> {
    std::fs::hard_link(staged, final_path)?;
    std::fs::remove_file(staged)
}

#[cfg(windows)]
mod windows_security {
    use super::*;
    use std::ffi::c_void;
    use std::os::windows::ffi::OsStrExt;
    use std::os::windows::io::FromRawHandle;
    use windows_sys::Win32::Foundation::{
        CloseHandle, ERROR_ALREADY_EXISTS, GENERIC_READ, GENERIC_WRITE, INVALID_HANDLE_VALUE,
        LocalFree,
    };
    use windows_sys::Win32::Security::Authorization::{
        ConvertStringSecurityDescriptorToSecurityDescriptorW, GetNamedSecurityInfoW,
        SDDL_REVISION_1, SE_FILE_OBJECT, SetNamedSecurityInfoW,
    };
    use windows_sys::Win32::Security::{
        ACCESS_ALLOWED_ACE, CreateWellKnownSid, DACL_SECURITY_INFORMATION, EqualSid, GetAce,
        GetSecurityDescriptorControl, GetSecurityDescriptorDacl, GetTokenInformation,
        OWNER_SECURITY_INFORMATION, PROTECTED_DACL_SECURITY_INFORMATION, PSECURITY_DESCRIPTOR,
        PSID, SE_DACL_PROTECTED, SECURITY_ATTRIBUTES, SECURITY_MAX_SID_SIZE, TOKEN_QUERY,
        TOKEN_USER, TokenUser, WinCreatorOwnerRightsSid, WinLocalSystemSid,
    };
    use windows_sys::Win32::Storage::FileSystem::{
        CREATE_NEW, CreateDirectoryW, CreateFileW, FILE_ALL_ACCESS, FILE_ATTRIBUTE_NORMAL,
        FILE_ATTRIBUTE_REPARSE_POINT, FILE_FLAG_OPEN_REPARSE_POINT, GetFileAttributesW,
        INVALID_FILE_ATTRIBUTES, MoveFileW,
    };
    use windows_sys::Win32::System::Threading::{GetCurrentProcess, OpenProcessToken};

    const OWNER_ONLY_SDDL: &str = "D:P(A;;FA;;;SY)(A;;FA;;;OW)";
    const ACCESS_ALLOWED_ACE_TYPE: u8 = 0;
    const INHERITED_ACE: u8 = 0x10;

    pub fn create_directory(path: &Path) -> std::io::Result<()> {
        let parent = path
            .parent()
            .ok_or_else(|| std::io::Error::other("credential directory has no parent"))?;
        std::fs::create_dir_all(parent)?;
        let wide = wide_path(path);
        with_security_attributes(|attributes| {
            if unsafe { CreateDirectoryW(wide.as_ptr(), attributes) } == 0 {
                let error = std::io::Error::last_os_error();
                if error.raw_os_error() != Some(ERROR_ALREADY_EXISTS as i32) {
                    return Err(error);
                }
            }
            Ok(())
        })?;
        validate_node_type(path, true)?;
        apply_owner_only_dacl(path)?;
        validate(path, true)
    }

    pub fn create_file(path: &Path) -> std::io::Result<File> {
        let wide = wide_path(path);
        let handle = with_security_attributes(|attributes| {
            let handle = unsafe {
                CreateFileW(
                    wide.as_ptr(),
                    GENERIC_READ | GENERIC_WRITE,
                    0,
                    attributes,
                    CREATE_NEW,
                    FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT,
                    std::ptr::null_mut(),
                )
            };
            if handle == INVALID_HANDLE_VALUE {
                Err(std::io::Error::last_os_error())
            } else {
                Ok(handle)
            }
        })?;
        // CreateFileW returned an owned handle and File closes it.
        let file = unsafe { File::from_raw_handle(handle) };
        validate(path, false)?;
        Ok(file)
    }

    pub fn validate(path: &Path, directory: bool) -> std::io::Result<()> {
        validate_node_type(path, directory)?;
        let wide = wide_path(path);
        validate_owner_and_dacl(&wide)
    }

    pub fn publish(staged: &Path, final_path: &Path) -> std::io::Result<()> {
        let staged = wide_path(staged);
        let final_path = wide_path(final_path);
        if unsafe { MoveFileW(staged.as_ptr(), final_path.as_ptr()) } == 0 {
            Err(std::io::Error::last_os_error())
        } else {
            Ok(())
        }
    }

    fn validate_node_type(path: &Path, directory: bool) -> std::io::Result<()> {
        let metadata = std::fs::symlink_metadata(path)?;
        if metadata.file_type().is_symlink()
            || (directory && !metadata.is_dir())
            || (!directory && !metadata.is_file())
        {
            return Err(std::io::Error::other("credential path has an unsafe type"));
        }
        let wide = wide_path(path);
        let attributes = unsafe { GetFileAttributesW(wide.as_ptr()) };
        if attributes == INVALID_FILE_ATTRIBUTES {
            return Err(std::io::Error::last_os_error());
        }
        if attributes & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
            return Err(std::io::Error::other("credential path is a reparse point"));
        }
        Ok(())
    }

    fn apply_owner_only_dacl(path: &Path) -> std::io::Result<()> {
        let wide = wide_path(path);
        with_security_descriptor(|descriptor| {
            let mut present = 0;
            let mut defaulted = 0;
            let mut dacl = std::ptr::null_mut();
            if unsafe {
                GetSecurityDescriptorDacl(descriptor, &mut present, &mut dacl, &mut defaulted)
            } == 0
                || present == 0
                || dacl.is_null()
            {
                return Err(std::io::Error::last_os_error());
            }
            let result = unsafe {
                SetNamedSecurityInfoW(
                    wide.as_ptr(),
                    SE_FILE_OBJECT,
                    DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    dacl,
                    std::ptr::null_mut(),
                )
            };
            if result == 0 {
                Ok(())
            } else {
                Err(std::io::Error::from_raw_os_error(result as i32))
            }
        })
    }

    fn validate_owner_and_dacl(wide: &[u16]) -> std::io::Result<()> {
        let mut owner: PSID = std::ptr::null_mut();
        let mut dacl = std::ptr::null_mut();
        let mut descriptor: PSECURITY_DESCRIPTOR = std::ptr::null_mut();
        let result = unsafe {
            GetNamedSecurityInfoW(
                wide.as_ptr(),
                SE_FILE_OBJECT,
                OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
                &mut owner,
                std::ptr::null_mut(),
                &mut dacl,
                std::ptr::null_mut(),
                &mut descriptor,
            )
        };
        if result != 0 {
            return Err(std::io::Error::from_raw_os_error(result as i32));
        }
        let validation = (|| {
            if owner.is_null() || dacl.is_null() {
                return Err(std::io::Error::other("credential DACL is absent"));
            }
            let current_user = current_user_sid()?;
            if unsafe { EqualSid(owner, current_user.as_ptr() as PSID) } == 0 {
                return Err(std::io::Error::other("credential path has the wrong owner"));
            }
            let mut control = 0;
            let mut revision = 0;
            if unsafe { GetSecurityDescriptorControl(descriptor, &mut control, &mut revision) } == 0
            {
                return Err(std::io::Error::last_os_error());
            }
            if control & SE_DACL_PROTECTED == 0 {
                return Err(std::io::Error::other("credential DACL inherits access"));
            }
            validate_aces(dacl)
        })();
        unsafe {
            LocalFree(descriptor);
        }
        validation
    }

    fn validate_aces(dacl: *mut windows_sys::Win32::Security::ACL) -> std::io::Result<()> {
        let acl = unsafe { &*dacl };
        if acl.AceCount != 2 {
            return Err(std::io::Error::other(
                "credential DACL grants unexpected principals",
            ));
        }
        let system = well_known_sid(WinLocalSystemSid)?;
        let owner_rights = well_known_sid(WinCreatorOwnerRightsSid)?;
        let mut saw_system = false;
        let mut saw_owner = false;
        for index in 0..u32::from(acl.AceCount) {
            let mut raw_ace = std::ptr::null_mut::<c_void>();
            if unsafe { GetAce(dacl, index, &mut raw_ace) } == 0 {
                return Err(std::io::Error::last_os_error());
            }
            let ace = unsafe { &*(raw_ace as *const ACCESS_ALLOWED_ACE) };
            if ace.Header.AceType != ACCESS_ALLOWED_ACE_TYPE
                || ace.Header.AceFlags & INHERITED_ACE != 0
                || ace.Mask != FILE_ALL_ACCESS
            {
                return Err(std::io::Error::other("credential DACL is not owner-only"));
            }
            let sid = std::ptr::addr_of!(ace.SidStart) as PSID;
            if unsafe { EqualSid(sid, system.as_ptr() as PSID) } != 0 {
                saw_system = true;
            } else if unsafe { EqualSid(sid, owner_rights.as_ptr() as PSID) } != 0 {
                saw_owner = true;
            } else {
                return Err(std::io::Error::other(
                    "credential DACL grants an unexpected principal",
                ));
            }
        }
        if saw_system && saw_owner {
            Ok(())
        } else {
            Err(std::io::Error::other(
                "credential DACL omits the owner or SYSTEM",
            ))
        }
    }

    fn current_user_sid() -> std::io::Result<Vec<usize>> {
        let mut token = std::ptr::null_mut();
        if unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) } == 0 {
            return Err(std::io::Error::last_os_error());
        }
        let result = (|| {
            let mut bytes = 0;
            unsafe {
                GetTokenInformation(token, TokenUser, std::ptr::null_mut(), 0, &mut bytes);
            }
            if bytes == 0 {
                return Err(std::io::Error::last_os_error());
            }
            let words = (bytes as usize).div_ceil(std::mem::size_of::<usize>());
            let mut buffer = vec![0usize; words];
            if unsafe {
                GetTokenInformation(
                    token,
                    TokenUser,
                    buffer.as_mut_ptr().cast(),
                    bytes,
                    &mut bytes,
                )
            } == 0
            {
                return Err(std::io::Error::last_os_error());
            }
            let user = unsafe { &*(buffer.as_ptr() as *const TOKEN_USER) };
            let sid_length = unsafe { windows_sys::Win32::Security::GetLengthSid(user.User.Sid) };
            if sid_length == 0 {
                return Err(std::io::Error::last_os_error());
            }
            let sid_words = (sid_length as usize).div_ceil(std::mem::size_of::<usize>());
            let mut sid = vec![0usize; sid_words];
            if unsafe {
                windows_sys::Win32::Security::CopySid(
                    sid_length,
                    sid.as_mut_ptr().cast(),
                    user.User.Sid,
                )
            } == 0
            {
                return Err(std::io::Error::last_os_error());
            }
            Ok(sid)
        })();
        unsafe {
            CloseHandle(token);
        }
        result
    }

    fn well_known_sid(kind: i32) -> std::io::Result<Vec<usize>> {
        let bytes = SECURITY_MAX_SID_SIZE as usize;
        let words = bytes.div_ceil(std::mem::size_of::<usize>());
        let mut buffer = vec![0usize; words];
        let mut length = SECURITY_MAX_SID_SIZE;
        if unsafe {
            CreateWellKnownSid(
                kind,
                std::ptr::null_mut(),
                buffer.as_mut_ptr().cast(),
                &mut length,
            )
        } == 0
        {
            return Err(std::io::Error::last_os_error());
        }
        Ok(buffer)
    }

    fn with_security_attributes<T>(
        action: impl FnOnce(*const SECURITY_ATTRIBUTES) -> std::io::Result<T>,
    ) -> std::io::Result<T> {
        with_security_descriptor(|descriptor| {
            let attributes = SECURITY_ATTRIBUTES {
                nLength: std::mem::size_of::<SECURITY_ATTRIBUTES>() as u32,
                lpSecurityDescriptor: descriptor,
                bInheritHandle: 0,
            };
            action(&attributes)
        })
    }

    fn with_security_descriptor<T>(
        action: impl FnOnce(PSECURITY_DESCRIPTOR) -> std::io::Result<T>,
    ) -> std::io::Result<T> {
        let sddl = OWNER_ONLY_SDDL
            .encode_utf16()
            .chain(std::iter::once(0))
            .collect::<Vec<_>>();
        let mut descriptor = std::ptr::null_mut();
        if unsafe {
            ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl.as_ptr(),
                SDDL_REVISION_1,
                &mut descriptor,
                std::ptr::null_mut(),
            )
        } == 0
        {
            return Err(std::io::Error::last_os_error());
        }
        let result = action(descriptor);
        unsafe {
            LocalFree(descriptor);
        }
        result
    }

    fn wide_path(path: &Path) -> Vec<u16> {
        path.as_os_str()
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn records_are_immutable_provider_bound_and_owner_only() {
        let directory = tempfile::tempdir().unwrap();
        let store = CredentialStore::new(directory.path().join("credentials")).unwrap();
        let reference = store
            .write(&Credential::api_key("openai", "sk-test-secret"))
            .unwrap();
        assert_eq!(
            store.read(&reference, "openai").unwrap(),
            Credential::api_key("openai", "sk-test-secret")
        );
        assert!(store.read(&reference, "gemini").is_err());
        assert!(
            store
                .write(&Credential::api_key("gemini", "key-two"))
                .is_ok()
        );

        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            assert_eq!(
                std::fs::metadata(store.directory()).unwrap().mode() & 0o777,
                0o700
            );
            assert_eq!(
                std::fs::metadata(store.directory().join(reference))
                    .unwrap()
                    .mode()
                    & 0o777,
                0o600
            );
        }
    }

    #[test]
    fn malformed_oversized_and_linked_records_fail_closed() {
        let directory = tempfile::tempdir().unwrap();
        let store = CredentialStore::new(directory.path().join("credentials")).unwrap();
        assert!(store.read("../secret", "openai").is_err());

        let reference = format!("{REFERENCE_PREFIX}{}.json", "a".repeat(32));
        let path = store.directory().join(&reference);
        std::fs::write(&path, vec![b'x'; MAX_RECORD_BYTES as usize + 1]).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        }
        assert!(store.read(&reference, "openai").is_err());

        #[cfg(unix)]
        {
            let linked = format!("{REFERENCE_PREFIX}{}.json", "b".repeat(32));
            std::os::unix::fs::symlink(&path, store.directory().join(&linked)).unwrap();
            assert!(store.read(&linked, "openai").is_err());
        }
    }

    #[test]
    fn cleanup_removes_only_staged_and_unreferenced_credentials() {
        let directory = tempfile::tempdir().unwrap();
        let store = CredentialStore::new(directory.path().join("credentials")).unwrap();
        let kept = store.write(&Credential::api_key("openai", "one")).unwrap();
        let removed = store.write(&Credential::api_key("gemini", "two")).unwrap();
        std::fs::write(store.directory().join("note.txt"), "keep").unwrap();
        store
            .cleanup_unreferenced(&HashSet::from([kept.clone()]))
            .unwrap();
        assert!(store.directory().join(kept).exists());
        assert!(!store.directory().join(removed).exists());
        assert!(store.directory().join("note.txt").exists());
    }

    #[test]
    fn publishing_a_secret_never_replaces_an_existing_record() {
        let directory = tempfile::tempdir().unwrap();
        let staged = directory.path().join("staged");
        let committed = directory.path().join("committed");
        std::fs::write(&staged, "new secret").unwrap();
        std::fs::write(&committed, "committed secret").unwrap();

        assert!(publish_secret_file(&staged, &committed).is_err());
        assert_eq!(
            std::fs::read_to_string(&committed).unwrap(),
            "committed secret"
        );
        assert_eq!(std::fs::read_to_string(&staged).unwrap(), "new secret");
    }

    #[test]
    fn strict_schema_rejects_unknown_fields_and_versions() {
        assert!(
            serde_json::from_str::<Credential>(
                r#"{"version":1,"provider":"openai","kind":"api_key","api_key":"x","extra":true}"#
            )
            .is_err()
        );
        let credential: Credential = serde_json::from_str(
            r#"{"version":2,"provider":"openai","kind":"api_key","api_key":"x"}"#,
        )
        .unwrap();
        assert!(credential.validate("openai").is_err());
    }

    #[test]
    fn native_state_root_uses_the_platform_directory_api() {
        let root = default_state_root().unwrap();
        assert!(root.is_absolute());
        #[cfg(target_os = "linux")]
        assert!(root.ends_with(Path::new(".local/state/vadgr")) || root.ends_with("vadgr"));
    }
}
