//! Database filesystem behavior that must be identical on every host.

use vadgr_daemon::db::Db;

#[test]
fn opening_a_database_creates_its_missing_parent_directories() {
    let root = tempfile::tempdir().unwrap();
    let path = root.path().join("state").join("nested").join("vadgr.db");

    Db::open(&path).unwrap();

    assert!(path.is_file());
}
