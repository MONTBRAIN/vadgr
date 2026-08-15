//! Host platform reporting for public API responses.

/// The machine platform used by `GET /api/health`.
pub fn machine_platform() -> &'static str {
    classify_platform(std::env::consts::OS, is_wsl())
}

/// The setup platform kept by the transitional computer-use response.
pub fn computer_use_platform() -> &'static str {
    if is_wsl() { "wsl2" } else { "native" }
}

fn is_wsl() -> bool {
    if std::env::consts::OS != "linux" {
        return false;
    }
    if std::env::var_os("WSL_DISTRO_NAME").is_some() || std::env::var_os("WSL_INTEROP").is_some() {
        return true;
    }
    linux_release_mentions_microsoft()
}

#[cfg(target_os = "linux")]
fn linux_release_mentions_microsoft() -> bool {
    std::fs::read_to_string("/proc/sys/kernel/osrelease")
        .or_else(|_| std::fs::read_to_string("/proc/version"))
        .map(|value| value.to_ascii_lowercase().contains("microsoft"))
        .unwrap_or(false)
}

#[cfg(not(target_os = "linux"))]
fn linux_release_mentions_microsoft() -> bool {
    false
}

fn classify_platform(os: &str, wsl: bool) -> &'static str {
    if os == "linux" && wsl {
        return "wsl";
    }
    match os {
        "macos" => "macos",
        "windows" => "windows",
        _ => "linux",
    }
}

#[cfg(test)]
mod tests {
    use super::classify_platform;

    #[test]
    fn public_platform_vocabulary_covers_each_supported_host() {
        assert_eq!(classify_platform("linux", false), "linux");
        assert_eq!(classify_platform("macos", false), "macos");
        assert_eq!(classify_platform("windows", false), "windows");
        assert_eq!(classify_platform("linux", true), "wsl");
        assert_eq!(classify_platform("windows", true), "windows");
    }
}
