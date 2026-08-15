use crate::engine::types::ProviderError;
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::ffi::OsString;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Arc;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OAuthBlock {
    pub access_token: String,
    pub refresh_token: String,
    #[serde(default)]
    pub expires_at: Option<u64>,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

#[async_trait]
pub trait CredentialStore: Send + Sync {
    async fn load(&self) -> Result<Option<OAuthBlock>, ProviderError>;
    async fn save(&self, value: &OAuthBlock) -> Result<(), ProviderError>;
}

#[cfg(not(target_os = "macos"))]
pub fn native_store() -> Result<Arc<dyn CredentialStore>, ProviderError> {
    Ok(Arc::new(FileCredentialStore::native()?))
}

#[cfg(target_os = "macos")]
pub fn native_store() -> Result<Arc<dyn CredentialStore>, ProviderError> {
    Ok(Arc::new(KeychainCredentialStore::native()?))
}

#[derive(Clone, Debug)]
pub struct FileCredentialStore {
    path: PathBuf,
}

impl FileCredentialStore {
    pub fn native() -> Result<Self, ProviderError> {
        Ok(Self {
            path: claude_credentials_path()?,
        })
    }

    pub fn new(path: PathBuf) -> Self {
        Self { path }
    }
}

#[async_trait]
impl CredentialStore for FileCredentialStore {
    async fn load(&self) -> Result<Option<OAuthBlock>, ProviderError> {
        let path = self.path.clone();
        tokio::task::spawn_blocking(move || load_file(&path))
            .await
            .map_err(|error| ProviderError::CredentialStore(error.to_string()))?
    }

    async fn save(&self, value: &OAuthBlock) -> Result<(), ProviderError> {
        let path = self.path.clone();
        let value = value.clone();
        tokio::task::spawn_blocking(move || save_file(&path, &value))
            .await
            .map_err(|error| ProviderError::CredentialStore(error.to_string()))?
    }
}

fn load_file(path: &Path) -> Result<Option<OAuthBlock>, ProviderError> {
    let bytes = match std::fs::read(path) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(ProviderError::CredentialStore(error.to_string())),
    };
    parse_document(&bytes)
}

fn parse_document(bytes: &[u8]) -> Result<Option<OAuthBlock>, ProviderError> {
    let doc: Value = serde_json::from_slice(bytes)
        .map_err(|error| ProviderError::InvalidCredentials(error.to_string()))?;
    let Some(block) = doc.get("claudeAiOauth") else {
        return Err(ProviderError::InvalidCredentials(
            "missing claudeAiOauth object".to_owned(),
        ));
    };
    serde_json::from_value(block.clone())
        .map(Some)
        .map_err(|error| ProviderError::InvalidCredentials(error.to_string()))
}

#[cfg(target_os = "macos")]
struct KeychainCredentialStore {
    account: String,
}

#[cfg(target_os = "macos")]
impl KeychainCredentialStore {
    const SERVICE: &'static str = "Claude Code-credentials";

    fn native() -> Result<Self, ProviderError> {
        let account = std::env::var("USER")
            .or_else(|_| std::env::var("LOGNAME"))
            .map_err(|_| ProviderError::CredentialStore("no native macOS account".to_owned()))?;
        Ok(Self { account })
    }
}

#[cfg(target_os = "macos")]
#[async_trait]
impl CredentialStore for KeychainCredentialStore {
    async fn load(&self) -> Result<Option<OAuthBlock>, ProviderError> {
        let account = self.account.clone();
        tokio::task::spawn_blocking(move || {
            match security_framework::passwords::get_generic_password(Self::SERVICE, &account) {
                Ok(bytes) => parse_document(&bytes),
                Err(error) if error.code() == security_framework_sys::base::errSecItemNotFound => {
                    Ok(None)
                }
                Err(error) => Err(ProviderError::CredentialStore(error.to_string())),
            }
        })
        .await
        .map_err(|error| ProviderError::CredentialStore(error.to_string()))?
    }

    async fn save(&self, value: &OAuthBlock) -> Result<(), ProviderError> {
        let account = self.account.clone();
        let value = value.clone();
        tokio::task::spawn_blocking(move || {
            let mut document = match security_framework::passwords::get_generic_password(
                Self::SERVICE,
                &account,
            ) {
                Ok(bytes) => serde_json::from_slice::<Value>(&bytes)
                    .map_err(|error| ProviderError::InvalidCredentials(error.to_string()))?,
                Err(error) if error.code() == security_framework_sys::base::errSecItemNotFound => {
                    Value::Object(Map::new())
                }
                Err(error) => return Err(ProviderError::CredentialStore(error.to_string())),
            };
            let root = document.as_object_mut().ok_or_else(|| {
                ProviderError::InvalidCredentials(
                    "credential document must be an object".to_owned(),
                )
            })?;
            root.insert(
                "claudeAiOauth".to_owned(),
                serde_json::to_value(value)
                    .map_err(|error| ProviderError::InvalidCredentials(error.to_string()))?,
            );
            let bytes = serde_json::to_vec(&document)
                .map_err(|error| ProviderError::InvalidCredentials(error.to_string()))?;
            security_framework::passwords::set_generic_password(Self::SERVICE, &account, &bytes)
                .map_err(|error| ProviderError::CredentialStore(error.to_string()))
        })
        .await
        .map_err(|error| ProviderError::CredentialStore(error.to_string()))?
    }
}

fn save_file(path: &Path, block: &OAuthBlock) -> Result<(), ProviderError> {
    let mut doc = match std::fs::read(path) {
        Ok(bytes) => serde_json::from_slice::<Value>(&bytes)
            .map_err(|error| ProviderError::InvalidCredentials(error.to_string()))?,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Value::Object(Map::new()),
        Err(error) => return Err(ProviderError::CredentialStore(error.to_string())),
    };
    let root = doc.as_object_mut().ok_or_else(|| {
        ProviderError::InvalidCredentials("credential document must be an object".to_owned())
    })?;
    root.insert(
        "claudeAiOauth".to_owned(),
        serde_json::to_value(block)
            .map_err(|error| ProviderError::InvalidCredentials(error.to_string()))?,
    );
    let parent = path.parent().ok_or_else(|| {
        ProviderError::CredentialStore("credential path has no parent".to_owned())
    })?;
    std::fs::create_dir_all(parent)
        .map_err(|error| ProviderError::CredentialStore(error.to_string()))?;
    let file_name = path
        .file_name()
        .ok_or_else(|| ProviderError::CredentialStore("credential path has no name".to_owned()))?;
    let mut temporary_name = OsString::from(".");
    temporary_name.push(file_name);
    temporary_name.push(format!(".{}.tmp", uuid::Uuid::new_v4()));
    let temporary = parent.join(temporary_name);
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)
        .map_err(|error| ProviderError::CredentialStore(error.to_string()))?;
    file.write_all(
        &serde_json::to_vec_pretty(&doc)
            .map_err(|error| ProviderError::InvalidCredentials(error.to_string()))?,
    )
    .and_then(|_| file.sync_all())
    .map_err(|error| ProviderError::CredentialStore(error.to_string()))?;
    drop(file);
    if let Err(error) = replace_file(&temporary, path) {
        let _ = std::fs::remove_file(&temporary);
        return Err(ProviderError::CredentialStore(error.to_string()));
    }
    Ok(())
}

fn claude_credentials_path() -> Result<PathBuf, ProviderError> {
    credentials_path_from(
        std::env::var_os("HOME"),
        std::env::var_os("USERPROFILE"),
        std::env::consts::OS,
    )
    .ok_or_else(|| ProviderError::CredentialStore("no native user home".to_owned()))
}

fn credentials_path_from(
    home: Option<OsString>,
    user_profile: Option<OsString>,
    os: &str,
) -> Option<PathBuf> {
    let root = if os == "windows" { user_profile } else { home }?;
    let root = PathBuf::from(root);
    root.is_absolute()
        .then(|| root.join(".claude").join(".credentials.json"))
}

#[cfg(not(windows))]
fn replace_file(source: &Path, destination: &Path) -> std::io::Result<()> {
    std::fs::rename(source, destination)
}

#[cfg(windows)]
fn replace_file(source: &Path, destination: &Path) -> std::io::Result<()> {
    use std::iter::once;
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW,
    };
    let source: Vec<u16> = source.as_os_str().encode_wide().chain(once(0)).collect();
    let destination: Vec<u16> = destination
        .as_os_str()
        .encode_wide()
        .chain(once(0))
        .collect();
    let result = unsafe {
        MoveFileExW(
            source.as_ptr(),
            destination.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if result == 0 {
        Err(std::io::Error::last_os_error())
    } else {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::{CredentialStore, FileCredentialStore, OAuthBlock, credentials_path_from};
    use std::ffi::OsString;
    use std::path::Path;

    #[tokio::test]
    async fn file_store_preserves_unrelated_keys() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("credentials.json");
        std::fs::write(&path, r#"{"other":{"kept":true}}"#).unwrap();
        let store = FileCredentialStore::new(path.clone());
        let value = OAuthBlock {
            access_token: "access".to_owned(),
            refresh_token: "refresh".to_owned(),
            expires_at: Some(10),
            extra: serde_json::Map::from_iter([("scope".to_owned(), serde_json::json!("user"))]),
        };
        store.save(&value).await.unwrap();
        let doc: serde_json::Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        assert_eq!(doc["other"]["kept"], true);
        assert_eq!(doc["claudeAiOauth"]["scope"], "user");
        assert_eq!(store.load().await.unwrap().unwrap().access_token, "access");
    }

    #[test]
    fn native_home_does_not_cross_operating_systems() {
        assert_eq!(
            credentials_path_from(Some("/home/a".into()), Some("C:\\Users\\a".into()), "linux")
                .unwrap(),
            Path::new("/home/a")
                .join(".claude")
                .join(".credentials.json")
        );
        assert!(credentials_path_from(Some("/mnt/c/Users/a".into()), None, "windows").is_none());
    }

    #[cfg(unix)]
    #[test]
    fn unix_home_keeps_non_utf8_bytes() {
        use std::os::unix::ffi::OsStringExt;
        let home = OsString::from_vec(b"/tmp/user-\xff".to_vec());
        let path = credentials_path_from(Some(home.clone()), None, "linux").unwrap();
        assert_eq!(path.parent().unwrap().parent().unwrap().as_os_str(), home);
    }
}
