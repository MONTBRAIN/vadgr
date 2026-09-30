use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    println!("cargo:rerun-if-env-changed=VADGR_RELEASE_PAYLOAD_BUILD");
    println!("cargo:rerun-if-env-changed=VADGR_RELEASE_PROFILE");
    let target = env::var("TARGET").expect("Cargo target is required");
    assert!(
        matches!(
            target.as_str(),
            "x86_64-pc-windows-msvc"
                | "aarch64-pc-windows-msvc"
                | "x86_64-apple-darwin"
                | "aarch64-apple-darwin"
                | "x86_64-unknown-linux-gnu"
                | "aarch64-unknown-linux-gnu"
        ),
        "unsupported CUA release target"
    );
    let root =
        PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").expect("Cargo source root is required"));
    let profile = env::var("VADGR_RELEASE_PROFILE").ok();
    let qualification = env::var_os("CARGO_FEATURE_LINUX_UNSIGNED_QUALIFICATION").is_some();
    for name in [
        "VADGR_QUALIFICATION_SOURCE_COMMIT",
        "VADGR_QUALIFICATION_SOURCE_TREE",
    ] {
        println!("cargo:rerun-if-env-changed={name}");
    }
    if qualification {
        assert_eq!(
            env::consts::OS,
            "linux",
            "qualification requires a native Linux builder"
        );
        assert!(
            target.ends_with("-unknown-linux-gnu")
                && env::var("HOST").as_deref() == Ok(target.as_str()),
            "qualification requires a native Linux target"
        );
        assert!(
            matches!(profile.as_deref(), Some("linux-x86_64" | "linux-aarch64")),
            "qualification requires an explicit native Linux profile"
        );
        assert!(
            env::var_os("CARGO_FEATURE_RELEASE_VERIFIER").is_none(),
            "qualification cannot build a release verifier"
        );
        let kernel = fs::read_to_string("/proc/sys/kernel/osrelease")
            .expect("native Linux kernel identity is required");
        assert!(
            !kernel.to_ascii_lowercase().contains("microsoft"),
            "WSL qualification refused"
        );
        for name in [
            "VADGR_QUALIFICATION_SOURCE_COMMIT",
            "VADGR_QUALIFICATION_SOURCE_TREE",
        ] {
            let value = env::var(name).expect("qualification source identity is required");
            assert!(
                value.len() == 40
                    && value
                        .bytes()
                        .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)),
                "qualification source identity must be a full lowercase Git identity"
            );
            println!("cargo:rustc-env={name}={value}");
        }
    }
    if target.ends_with("-unknown-linux-gnu") {
        println!("cargo:rustc-link-arg=-Wl,--undefined=VADGR_BUILD_POLICY_NOTE");
    }
    if let Some(profile) = &profile {
        let (system, architecture) = profile.split_once('-').expect("invalid release profile");
        let suffix = match system {
            "windows" => "pc-windows-msvc",
            "macos" => "apple-darwin",
            "linux" | "wsl" => "unknown-linux-gnu",
            _ => panic!("unknown release profile"),
        };
        assert!(
            matches!(architecture, "x86_64" | "aarch64"),
            "unsupported release architecture"
        );
        assert_eq!(
            target,
            format!("{architecture}-{suffix}"),
            "release profile differs from Rust target"
        );
    }
    let lock = profile.as_ref().map_or_else(
        || format!("packaging/cua/locks/{target}.lock"),
        |profile| format!("packaging/cua/profile-locks/{profile}.lock"),
    );
    let manifest = "packaging/cua/native-wheel-manifest.json";
    for name in [&lock, manifest] {
        println!("cargo:rerun-if-changed={name}");
    }
    let required = match env::var("VADGR_RELEASE_PAYLOAD_BUILD").as_deref() {
        Ok("1") => true,
        Err(env::VarError::NotPresent) => false,
        _ => panic!("VADGR_RELEASE_PAYLOAD_BUILD must be absent or 1"),
    };
    let present = [&lock, manifest].map(|name| root.join(name).is_file());
    assert!(
        profile.is_none() || present[0],
        "release profile has no reviewed lock; fallback refused"
    );
    assert!(
        !present[0] || present[1],
        "a reviewed target lock requires the wheel manifest"
    );
    assert!(
        !required || present[0],
        "release payload build requires reviewed per-target wheel inputs"
    );
    let mut output = format!(
        "const RELEASE_TARGET_UNPROMOTED: bool = {};\n",
        present[1] && !present[0]
    );
    output.push_str(&format!(
        "const RELEASE_PROFILE: Option<&str> = {profile:?};\n"
    ));
    for (name, path) in [
        ("RELEASE_REQUIREMENTS", lock.as_str()),
        ("RELEASE_WHEEL_MANIFEST", manifest),
    ] {
        if present[0] {
            let metadata = fs::symlink_metadata(root.join(path)).expect("release input metadata");
            assert!(
                metadata.is_file() && !metadata.file_type().is_symlink(),
                "linked release input refused"
            );
            output.push_str(&format!("const {name}: Option<&[u8]> = Some(include_bytes!(concat!(env!(\"CARGO_MANIFEST_DIR\"), \"/{path}\")));\n"));
        } else {
            output.push_str(&format!("const {name}: Option<&[u8]> = None;\n"));
        }
    }
    for (name, path) in [
        (
            "RELEASE_PROFILE_INPUTS",
            "packaging/cua/profile-inputs.json",
        ),
        (
            "RELEASE_PROFILE_CATALOG",
            "packaging/cua/cua-profile-catalog.json",
        ),
    ] {
        println!("cargo:rerun-if-changed={path}");
        if profile.is_some() {
            let metadata =
                fs::symlink_metadata(root.join(path)).expect("reviewed profile input is required");
            assert!(
                metadata.is_file() && !metadata.file_type().is_symlink(),
                "linked profile input refused"
            );
            output.push_str(&format!("const {name}: Option<&[u8]> = Some(include_bytes!(concat!(env!(\"CARGO_MANIFEST_DIR\"), \"/{path}\")));\n"));
        } else {
            output.push_str(&format!("const {name}: Option<&[u8]> = None;\n"));
        }
    }
    fs::write(
        PathBuf::from(env::var_os("OUT_DIR").expect("Cargo output root is required"))
            .join("cua_release_pins.rs"),
        output,
    )
    .expect("write compiled CUA input selection");
}
