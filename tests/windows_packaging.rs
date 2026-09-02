use std::path::PathBuf;

fn repo_file(relative: &str) -> String {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(relative);
    std::fs::read_to_string(path).unwrap()
}

#[test]
fn windows_package_is_per_user_and_owns_native_launch_entries() {
    let package = repo_file("packaging/windows/Package.wxs");
    assert!(package.contains("Scope=\"perUser\""));
    assert!(!package.contains("perUserOrMachine"));
    assert!(package.contains("Id=\"LocalAppDataFolder\""));
    assert!(package.contains("Name=\"Programs\""));
    assert!(package.contains("Target=\"[INSTALLFOLDER]vadgr-app.exe\""));
    assert!(package.contains("Software\\Microsoft\\Windows\\CurrentVersion\\Run"));
    assert!(package.contains("--daemon"));
    assert!(!package.contains("ProgramFilesFolder"));
    assert!(!package.contains("ServiceInstall"));
    let bundle = repo_file("packaging/windows/Bundle.wxs");
    assert!(!bundle.contains("WixStdBAScope"));
    let project = repo_file("packaging/windows/VadgrBundle.wixproj");
    assert!(project.contains("<OutputType>Bundle</OutputType>"));
    let msi_project = repo_file("packaging/windows/VadgrMsi.wixproj");
    assert!(msi_project.contains("$(GeneratedPayloadWxs)"));
    assert!(!msi_project.contains("WixToolset.Heat"));
    let generator = repo_file("scripts/generate_windows_payload_wxs.py");
    assert!(generator.contains("uuid.uuid5"));
    assert!(generator.contains("payload contains a link"));
}

#[test]
fn burn_owns_terms_progress_repair_uninstall_and_console_launch() {
    let bundle = repo_file("packaging/windows/Bundle.wxs");
    assert!(bundle.contains("WixStandardBootstrapperApplication"));
    assert!(bundle.contains("Theme=\"none\""));
    assert!(bundle.contains("ThemeFile=\"$(var.ThemeFile)\""));
    assert!(bundle.contains("LicenseFile=\"$(var.TermsRtf)\""));
    assert!(bundle.contains("SuppressRepair=\"no\""));
    assert!(bundle.contains("LaunchTarget=\"[InstallFolder]\\vadgr-app.exe\""));
    assert!(bundle.contains("Name=\"TERMSACCEPTED\" Value=\"1\""));
    assert!(bundle.contains("WixBundleInstalled OR WixBundleUILevel = 4"));
    assert!(bundle.contains("Name=\"BUNDLESOURCE\""));
    assert!(bundle.contains("<MsiPackage"));
    let package = repo_file("packaging/windows/Package.wxs");
    assert!(package.contains("Condition=\"Installed OR TERMSACCEPTED = 1\""));
    assert!(package.contains("Id=\"RecordTermsAcceptance\""));
    assert!(package.contains("Id=\"CacheInstallVehicle\""));
    assert!(package.contains("__cache-install-vehicle"));
    assert!(package.contains("Execute=\"commit\""));
    assert!(package.contains("HideTarget=\"yes\""));
    assert!(package.contains("AllowDowngrades=\"yes\""));
    let receipt = repo_file("packaging/windows/install-receipt.json");
    assert!(receipt.contains("cache/previous-setup.exe"));
}

#[test]
fn custom_setup_theme_covers_every_terminal_installer_state() {
    let theme = repo_file("packaging/windows/VadgrTheme.xml");
    for page in [
        "Loading", "Help", "Install", "Progress", "Modify", "Success", "Failure",
    ] {
        assert!(
            theme.contains(&format!("<Page Name=\"{page}\">")),
            "missing installer page: {page}"
        );
    }
    for control in [
        "EulaRichedit",
        "EulaAcceptCheckbox",
        "InstallButton",
        "OverallCalculatedProgressbar",
        "RepairButton",
        "UninstallButton",
        "LaunchButton",
        "FailureMessageText",
    ] {
        assert!(
            theme.contains(&format!("Name=\"{control}\"")),
            "missing installer control: {control}"
        );
    }
    assert!(
        theme.contains(
            "If Vadgr was already installed, that working installation remains available."
        )
    );
}

#[test]
fn candidate_build_refuses_an_incomplete_payload() {
    let build = repo_file("packaging/windows/build.ps1");
    for required in [
        "vadgr.exe",
        "vadgr-app.exe",
        "legal\\TERMS.txt",
        "legal\\THIRD-PARTY-NOTICES.txt",
        "README-OFFLINE.txt",
        "spdx.json",
    ] {
        assert!(
            build.contains(required),
            "missing required input: {required}"
        );
    }
    assert!(build.contains("StartsWith('{\\rtf')"));
    assert!(!build.contains("signtool"));
    assert!(
        !build
            .lines()
            .any(|line| line.trim() == "'release-manifest.json',"),
        "the manifest hashes the final setup and therefore cannot be embedded in that setup"
    );
}
