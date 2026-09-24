use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    println!("cargo:rerun-if-env-changed=VADGR_RELEASE_PAYLOAD_BUILD");
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
    let lock = format!("packaging/cua/locks/{target}.lock");
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
        present[0] == present[1],
        "the reviewed target lock and wheel manifest must arrive together"
    );
    assert!(
        !required || present[0],
        "release payload build requires reviewed per-target wheel inputs"
    );
    let mut output = String::new();
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
    fs::write(
        PathBuf::from(env::var_os("OUT_DIR").expect("Cargo output root is required"))
            .join("cua_release_pins.rs"),
        output,
    )
    .expect("write compiled CUA input selection");
}
