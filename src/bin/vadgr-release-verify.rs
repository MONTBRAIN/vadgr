//! Static bootstrap verifier used by the WSL installer.

use std::path::PathBuf;

fn main() {
    if let Err(error) = run() {
        eprintln!("release verification failed: {error:#}");
        std::process::exit(1);
    }
}

fn run() -> anyhow::Result<()> {
    let mut arguments = std::env::args_os().skip(1);
    let mut manifest = None;
    let mut signature = None;
    let mut artifact = None;
    let mut target = None;
    while let Some(argument) = arguments.next() {
        match argument.to_str() {
            Some("--manifest") => manifest = arguments.next().map(PathBuf::from),
            Some("--signature") => signature = arguments.next().map(PathBuf::from),
            Some("--artifact") => artifact = arguments.next().map(PathBuf::from),
            Some("--target") => {
                target = arguments.next().and_then(|value| value.into_string().ok())
            }
            _ => anyhow::bail!("unsupported verifier argument"),
        }
    }
    let manifest = manifest.ok_or_else(|| anyhow::anyhow!("--manifest is required"))?;
    let signature = signature.ok_or_else(|| anyhow::anyhow!("--signature is required"))?;
    let target = target.unwrap_or(vadgr_daemon::install::current_target()?);
    let verified = vadgr_daemon::install::VerifiedManifest::open(
        &manifest,
        &signature,
        vadgr_daemon::install::RELEASE_PUBLIC_KEY,
    )?;
    let row = verified.artifact_for_target(&target)?;
    if let Some(path) = artifact {
        if path.file_name().and_then(|value| value.to_str()) != Some(row.name.as_str()) {
            anyhow::bail!("the artifact name does not match the signed manifest");
        }
        verified.verify_bytes_at(&path, &row)?;
        if row.kind == "tar.gz" {
            vadgr_daemon::install::validate_tar_gz(&path)?;
        }
    }
    println!("{}", serde_json::to_string(&row)?);
    Ok(())
}
