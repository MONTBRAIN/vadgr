//! Bringing a machine's state to one root, before the daemon serves anything.
//!
//! **The hard part is not moving files. It is deciding what to do when two
//! machines' worth of state exists**, which is the normal case on any
//! installation that ran through the side-by-side releases: one database was
//! written by the daemon that is leaving and one by the daemon that stays.
//!
//! Every case is decided here rather than at the call site, and three of them
//! **refuse**. A daemon that starts empty because it could not reconcile is a
//! machine that has silently lost its history, and its owner finds out later.

use std::path::{Path, PathBuf};

use rusqlite::Connection;

/// What was found before anything was written.
#[derive(Debug, Default, PartialEq, Eq)]
pub struct Inventory {
    /// The target root's database, when the machine has already cut over.
    pub target: Option<PathBuf>,
    /// The database the departing daemon wrote.
    pub departing: Option<PathBuf>,
    /// The database the surviving daemon wrote beside it.
    pub surviving: Option<PathBuf>,
    /// The run journals the surviving daemon wrote outside the state root.
    pub legacy_runs: Option<PathBuf>,
}

/// What the consolidation decided to do.
#[derive(Debug, PartialEq, Eq)]
pub enum Plan {
    /// Nothing to bring across.
    Fresh,
    /// The machine has already cut over.
    AlreadyHere,
    /// Move one database in, and the journals beside it.
    Adopt { db: PathBuf, runs: Option<PathBuf> },
    /// Take the surviving database and insert the departing one's rows.
    Merge {
        keep: PathBuf,
        contribute: PathBuf,
        runs: Option<PathBuf>,
    },
}

/// Why the daemon will not start.
///
/// Each of these is a case where a rule would have to invent an answer. The
/// message names what was found and what to do, because a refusal a person
/// cannot act on is an outage rather than a safeguard.
#[derive(Debug, PartialEq, Eq)]
pub enum Refusal {
    /// The same run id in both databases.
    RunIdInBoth { id: String, a: PathBuf, b: PathBuf },
    /// The same device id in both databases.
    DeviceIdInBoth { id: String, a: PathBuf, b: PathBuf },
    /// The target root holds something this product did not write.
    TargetOccupied { root: PathBuf },
    /// A database could not be read at all.
    Unreadable { path: PathBuf, reason: String },
}

impl std::fmt::Display for Refusal {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::RunIdInBoth { id, a, b } => write!(
                f,
                "run {id} exists in both {} and {}. Two databases were expected to \
                 hold different runs, so this is a case the upgrade does not model. \
                 Nothing has been moved. Copy one of them aside and start again.",
                a.display(),
                b.display()
            ),
            Self::DeviceIdInBoth { id, a, b } => write!(
                f,
                "device {id} exists in both {} and {}. Nothing has been moved. Copy \
                 one of them aside and start again.",
                a.display(),
                b.display()
            ),
            Self::TargetOccupied { root } => write!(
                f,
                "{} exists and does not look like this product's state. Nothing has \
                 been moved. Point VADGR_STATE_HOME somewhere else, or move that \
                 directory aside.",
                root.display()
            ),
            Self::Unreadable { path, reason } => write!(
                f,
                "{} could not be read: {reason}. Nothing has been moved.",
                path.display()
            ),
        }
    }
}

/// Look, and write nothing.
///
/// The legacy locations are the ones the side-by-side releases actually used:
/// the departing daemon's database below its working directory, the surviving
/// daemon's beside it, and the run journals under the home directory.
pub fn take_inventory(root: &Path, working_dir: &Path, home: Option<&Path>) -> Inventory {
    let exists = |p: PathBuf| p.exists().then_some(p);
    Inventory {
        target: exists(root.join("vadgr.db")),
        departing: exists(working_dir.join("data").join("agent_forge.db")),
        surviving: exists(working_dir.join("data").join("vadgr-rust.db")),
        legacy_runs: home
            .map(|h| h.join(".vadgr").join("runs"))
            .filter(|p| p.is_dir()),
    }
}

/// Decide, and write nothing.
///
/// Separating the decision from the move is what makes a refusal safe: by the
/// time anything is on disk, every reason to stop has already been found.
pub fn decide(inventory: &Inventory, root: &Path) -> Result<Plan, Refusal> {
    if inventory.target.is_some() {
        return Ok(Plan::AlreadyHere);
    }
    if root.exists() && !crate::config::is_our_root(root) && !is_empty_dir(root) {
        return Err(Refusal::TargetOccupied {
            root: root.to_path_buf(),
        });
    }

    match (&inventory.departing, &inventory.surviving) {
        (None, None) => Ok(Plan::Fresh),
        (Some(db), None) | (None, Some(db)) => Ok(Plan::Adopt {
            db: db.clone(),
            runs: inventory.legacy_runs.clone(),
        }),
        (Some(departing), Some(surviving)) => {
            // The surviving schema is a strict superset, so it is the one that
            // is kept and the other contributes its rows. Ids are random per
            // daemon, so an id in both is not a collision this design models.
            if let Some(id) = shared_id(departing, surviving, "runs")? {
                return Err(Refusal::RunIdInBoth {
                    id,
                    a: departing.clone(),
                    b: surviving.clone(),
                });
            }
            if let Some(id) = shared_id(departing, surviving, "devices")? {
                return Err(Refusal::DeviceIdInBoth {
                    id,
                    a: departing.clone(),
                    b: surviving.clone(),
                });
            }
            Ok(Plan::Merge {
                keep: surviving.clone(),
                contribute: departing.clone(),
                runs: inventory.legacy_runs.clone(),
            })
        }
    }
}

fn is_empty_dir(path: &Path) -> bool {
    std::fs::read_dir(path)
        .map(|mut entries| entries.next().is_none())
        .unwrap_or(false)
}

/// The first id present in both databases' `table`, if any.
fn shared_id(a: &Path, b: &Path, table: &str) -> Result<Option<String>, Refusal> {
    let left = ids(a, table)?;
    if left.is_empty() {
        return Ok(None);
    }
    let right = ids(b, table)?;
    Ok(right.into_iter().find(|id| left.contains(id)))
}

fn ids(path: &Path, table: &str) -> Result<std::collections::HashSet<String>, Refusal> {
    let unreadable = |e: rusqlite::Error| Refusal::Unreadable {
        path: path.to_path_buf(),
        reason: e.to_string(),
    };
    let conn = Connection::open(path).map_err(unreadable)?;
    // A database that predates a table simply has none of its rows, which is
    // not an error: the departing daemon never had the provider tables.
    let present: i64 = conn
        .query_row(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?1",
            [table],
            |row| row.get(0),
        )
        .map_err(unreadable)?;
    if present == 0 {
        return Ok(Default::default());
    }
    let mut stmt = conn
        .prepare(&format!("SELECT id FROM {table}"))
        .map_err(unreadable)?;
    let rows = stmt
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(unreadable)?;
    let mut out = std::collections::HashSet::new();
    for row in rows {
        out.insert(row.map_err(unreadable)?);
    }
    Ok(out)
}

/// Carry out a plan.
///
/// **The final rename is the commit.** Everything is staged beside the target
/// first, so an interruption leaves the target absent and the sources untouched;
/// the next start finds the stage, discards it and begins again. A target that
/// can be observed half-populated is the failure this ordering removes, because
/// the daemon serves immediately afterwards.
///
/// Sources are removed **only after** the target is in place and readable.
pub fn apply(plan: &Plan, root: &Path) -> Result<(), Refusal> {
    fn io(path: &Path) -> impl Fn(std::io::Error) -> Refusal + '_ {
        move |e: std::io::Error| Refusal::Unreadable {
            path: path.to_path_buf(),
            reason: e.to_string(),
        }
    }

    let (db, runs, contribute) = match plan {
        Plan::Fresh | Plan::AlreadyHere => {
            std::fs::create_dir_all(root).map_err(io(root))?;
            return Ok(());
        }
        Plan::Adopt { db, runs } => (db.clone(), runs.clone(), None),
        Plan::Merge {
            keep,
            contribute,
            runs,
        } => (keep.clone(), runs.clone(), Some(contribute.clone())),
    };

    let stage = root.with_extension("staging");
    if stage.exists() {
        // A stage from an interrupted attempt is not state, it is debris.
        std::fs::remove_dir_all(&stage).map_err(io(&stage))?;
    }
    std::fs::create_dir_all(&stage).map_err(io(&stage))?;

    // Copy rather than rename, because the source may be on another filesystem
    // and a rename across one fails rather than falling back.
    let staged_db = stage.join("vadgr.db");
    copy_database(&db, &staged_db)?;
    if let Some(contribute) = contribute.as_ref() {
        contribute_rows(contribute, &staged_db)?;
    }
    if let Some(runs) = runs.as_ref() {
        copy_tree(runs, &stage.join("runs"))?;
    }

    // The commit. Everything above can be interrupted and leaves no target.
    std::fs::create_dir_all(root.parent().unwrap_or(root)).map_err(io(root))?;
    if root.exists() {
        // Only ever an empty directory here: `decide` refused anything else.
        std::fs::remove_dir(root).map_err(io(root))?;
    }
    std::fs::rename(&stage, root).map_err(io(&stage))?;

    // Verified, then the sources go. A source removed before the target is
    // readable is a machine with no history and no way back.
    verify(&root.join("vadgr.db"))?;
    for source in [Some(db), contribute].into_iter().flatten() {
        let _ = std::fs::remove_file(&source);
    }
    if let Some(runs) = runs {
        let _ = std::fs::remove_dir_all(&runs);
    }
    Ok(())
}

/// Copy a SQLite database and the two sidecars a live one leaves behind.
///
/// The write-ahead log holds committed rows that are not in the main file yet,
/// so copying the `.db` alone silently drops the most recent runs. That is not
/// hypothetical: it was found while assembling evidence during `0.4.7`.
fn copy_database(from: &Path, to: &Path) -> Result<(), Refusal> {
    let conn = Connection::open(from).map_err(|e| Refusal::Unreadable {
        path: from.to_path_buf(),
        reason: e.to_string(),
    })?;
    conn.execute_batch("PRAGMA wal_checkpoint(TRUNCATE);")
        .map_err(|e| Refusal::Unreadable {
            path: from.to_path_buf(),
            reason: e.to_string(),
        })?;
    drop(conn);
    std::fs::copy(from, to).map_err(|e| Refusal::Unreadable {
        path: from.to_path_buf(),
        reason: e.to_string(),
    })?;
    Ok(())
}

/// Insert the departing database's rows into the surviving one.
///
/// `decide` has already refused a shared id, so `INSERT` cannot collide. The
/// column list comes from the target rather than the source, because the source
/// has fewer columns and naming them explicitly is what keeps this correct when
/// a later release adds one.
fn contribute_rows(from: &Path, into: &Path) -> Result<(), Refusal> {
    let unreadable = |path: &Path| {
        let path = path.to_path_buf();
        move |e: rusqlite::Error| Refusal::Unreadable {
            path: path.clone(),
            reason: e.to_string(),
        }
    };
    let conn = Connection::open(into).map_err(unreadable(into))?;
    conn.execute(
        "ATTACH DATABASE ?1 AS departing",
        [from.to_string_lossy().as_ref()],
    )
    .map_err(unreadable(from))?;

    for table in ["runs", "devices"] {
        let source_has: i64 = conn
            .query_row(
                "SELECT count(*) FROM departing.sqlite_master WHERE type='table' AND name=?1",
                [table],
                |row| row.get(0),
            )
            .map_err(unreadable(from))?;
        if source_has == 0 {
            continue;
        }
        let columns = shared_columns(&conn, table).map_err(unreadable(into))?;
        if columns.is_empty() {
            continue;
        }
        let list = columns.join(", ");
        conn.execute_batch(&format!(
            "INSERT OR IGNORE INTO main.{table} ({list}) SELECT {list} FROM departing.{table};"
        ))
        .map_err(unreadable(into))?;
    }
    conn.execute_batch("DETACH DATABASE departing;")
        .map_err(unreadable(into))?;
    Ok(())
}

/// The columns both databases have, which is what can be carried across.
fn shared_columns(conn: &Connection, table: &str) -> rusqlite::Result<Vec<String>> {
    let names = |schema: &str| -> rusqlite::Result<Vec<String>> {
        let mut stmt = conn.prepare(&format!("PRAGMA {schema}.table_info({table})"))?;
        let rows = stmt.query_map([], |row| row.get::<_, String>(1))?;
        rows.collect()
    };
    let target = names("main")?;
    let source = names("departing")?;
    Ok(target.into_iter().filter(|c| source.contains(c)).collect())
}

fn copy_tree(from: &Path, to: &Path) -> Result<(), Refusal> {
    fn io(path: &Path) -> impl Fn(std::io::Error) -> Refusal + '_ {
        move |e: std::io::Error| Refusal::Unreadable {
            path: path.to_path_buf(),
            reason: e.to_string(),
        }
    }
    std::fs::create_dir_all(to).map_err(io(to))?;
    for entry in std::fs::read_dir(from).map_err(io(from))? {
        let entry = entry.map_err(io(from))?;
        let target = to.join(entry.file_name());
        if entry.path().is_dir() {
            copy_tree(&entry.path(), &target)?;
        } else {
            std::fs::copy(entry.path(), &target).map_err(io(&entry.path()))?;
        }
    }
    Ok(())
}

/// The target opens and answers, before any source is removed.
fn verify(db: &Path) -> Result<(), Refusal> {
    let unreadable = |e: rusqlite::Error| Refusal::Unreadable {
        path: db.to_path_buf(),
        reason: e.to_string(),
    };
    let conn = Connection::open(db).map_err(unreadable)?;
    conn.query_row("SELECT count(*) FROM sqlite_master", [], |row| {
        row.get::<_, i64>(0)
    })
    .map_err(unreadable)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sqlite(path: &Path, tables: &[(&str, &[&str])]) {
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        let conn = Connection::open(path).unwrap();
        for (table, ids) in tables {
            conn.execute_batch(&format!(
                "CREATE TABLE {table} (id TEXT PRIMARY KEY, title TEXT);"
            ))
            .unwrap();
            for id in *ids {
                conn.execute(
                    &format!("INSERT INTO {table} (id, title) VALUES (?1, 'x')"),
                    [id],
                )
                .unwrap();
            }
        }
    }

    fn temp() -> PathBuf {
        let p = std::env::temp_dir().join(format!("vadgr-migrate-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&p).unwrap();
        p
    }

    #[test]
    fn nothing_anywhere_is_a_clean_start() {
        let t = temp();
        let inv = take_inventory(&t.join("root"), &t.join("cwd"), None);
        assert_eq!(inv, Inventory::default());
        assert_eq!(decide(&inv, &t.join("root")).unwrap(), Plan::Fresh);
    }

    #[test]
    fn a_machine_that_already_cut_over_is_left_alone() {
        let t = temp();
        let root = t.join("root");
        sqlite(&root.join("vadgr.db"), &[("runs", &["r1"])]);
        let inv = take_inventory(&root, &t.join("cwd"), None);
        assert_eq!(decide(&inv, &root).unwrap(), Plan::AlreadyHere);
    }

    #[test]
    fn one_database_is_adopted_with_its_journals() {
        let t = temp();
        let (root, cwd, home) = (t.join("root"), t.join("cwd"), t.join("home"));
        sqlite(
            &cwd.join("data").join("agent_forge.db"),
            &[("runs", &["r1"])],
        );
        std::fs::create_dir_all(home.join(".vadgr").join("runs")).unwrap();
        let inv = take_inventory(&root, &cwd, Some(&home));
        match decide(&inv, &root).unwrap() {
            Plan::Adopt { db, runs } => {
                assert!(db.ends_with("agent_forge.db"));
                assert!(runs.unwrap().ends_with(Path::new(".vadgr").join("runs")));
            }
            other => panic!("expected an adoption, got {other:?}"),
        }
    }

    /// **The normal case on a real installation**: both daemons ran, so both
    /// databases exist and hold different runs.
    #[test]
    fn two_databases_with_different_runs_merge_into_the_surviving_one() {
        let t = temp();
        let (root, cwd) = (t.join("root"), t.join("cwd"));
        sqlite(
            &cwd.join("data").join("agent_forge.db"),
            &[("runs", &["old-1", "old-2"]), ("devices", &["d-old"])],
        );
        sqlite(
            &cwd.join("data").join("vadgr-rust.db"),
            &[("runs", &["new-1"]), ("devices", &["d-new"])],
        );
        let inv = take_inventory(&root, &cwd, None);
        match decide(&inv, &root).unwrap() {
            Plan::Merge {
                keep, contribute, ..
            } => {
                assert!(keep.ends_with("vadgr-rust.db"), "the superset is kept");
                assert!(contribute.ends_with("agent_forge.db"));
            }
            other => panic!("expected a merge, got {other:?}"),
        }
    }

    #[test]
    fn a_run_id_in_both_refuses_and_names_it() {
        let t = temp();
        let (root, cwd) = (t.join("root"), t.join("cwd"));
        sqlite(
            &cwd.join("data").join("agent_forge.db"),
            &[("runs", &["shared"])],
        );
        sqlite(
            &cwd.join("data").join("vadgr-rust.db"),
            &[("runs", &["shared"])],
        );
        let inv = take_inventory(&root, &cwd, None);
        match decide(&inv, &root).unwrap_err() {
            Refusal::RunIdInBoth { id, .. } => assert_eq!(id, "shared"),
            other => panic!("expected a run refusal, got {other:?}"),
        }
    }

    #[test]
    fn a_device_id_in_both_refuses_and_names_it() {
        let t = temp();
        let (root, cwd) = (t.join("root"), t.join("cwd"));
        sqlite(
            &cwd.join("data").join("agent_forge.db"),
            &[("runs", &["a"]), ("devices", &["same-phone"])],
        );
        sqlite(
            &cwd.join("data").join("vadgr-rust.db"),
            &[("runs", &["b"]), ("devices", &["same-phone"])],
        );
        let inv = take_inventory(&root, &cwd, None);
        match decide(&inv, &root).unwrap_err() {
            Refusal::DeviceIdInBoth { id, .. } => assert_eq!(id, "same-phone"),
            other => panic!("expected a device refusal, got {other:?}"),
        }
    }

    /// The target existing and not being ours is a user's data, not a place to
    /// write into.
    #[test]
    fn an_occupied_foreign_target_refuses() {
        let t = temp();
        let root = t.join("root");
        std::fs::create_dir_all(&root).unwrap();
        std::fs::write(root.join("someone-elses.txt"), b"x").unwrap();
        let inv = take_inventory(&root, &t.join("cwd"), None);
        assert!(matches!(
            decide(&inv, &root).unwrap_err(),
            Refusal::TargetOccupied { .. }
        ));
    }

    /// An empty directory is not occupied: an installer or a packager may have
    /// created it, and refusing there would block every managed deployment.
    #[test]
    fn an_empty_target_directory_is_not_occupied() {
        let t = temp();
        let root = t.join("root");
        std::fs::create_dir_all(&root).unwrap();
        let inv = take_inventory(&root, &t.join("cwd"), None);
        assert_eq!(decide(&inv, &root).unwrap(), Plan::Fresh);
    }

    /// A departing database has no provider tables at all, which is not an
    /// error: it never had them.
    #[test]
    fn a_missing_table_contributes_no_rows_rather_than_failing() {
        let t = temp();
        let (root, cwd) = (t.join("root"), t.join("cwd"));
        sqlite(
            &cwd.join("data").join("agent_forge.db"),
            &[("runs", &["r1"])],
        );
        sqlite(
            &cwd.join("data").join("vadgr-rust.db"),
            &[("runs", &["r2"]), ("devices", &["d"])],
        );
        let inv = take_inventory(&root, &cwd, None);
        assert!(matches!(decide(&inv, &root).unwrap(), Plan::Merge { .. }));
    }

    fn rows(db: &Path, table: &str) -> Vec<String> {
        let conn = Connection::open(db).unwrap();
        let mut stmt = conn
            .prepare(&format!("SELECT id FROM {table} ORDER BY id"))
            .unwrap();
        let out: Vec<String> = stmt
            .query_map([], |r| r.get::<_, String>(0))
            .unwrap()
            .map(|r| r.unwrap())
            .collect();
        out
    }

    /// **The case a real installation hits, end to end.** Both databases exist,
    /// each with its own runs, and after the move the machine has every one of
    /// them in one place.
    #[test]
    fn a_merge_keeps_every_run_from_both_databases() {
        let t = temp();
        let (root, cwd) = (t.join("root"), t.join("cwd"));
        sqlite(
            &cwd.join("data").join("agent_forge.db"),
            &[("runs", &["old-1", "old-2"]), ("devices", &["d-old"])],
        );
        sqlite(
            &cwd.join("data").join("vadgr-rust.db"),
            &[("runs", &["new-1"]), ("devices", &["d-new"])],
        );
        let inv = take_inventory(&root, &cwd, None);
        let plan = decide(&inv, &root).unwrap();
        apply(&plan, &root).unwrap();

        assert_eq!(
            rows(&root.join("vadgr.db"), "runs"),
            ["new-1", "old-1", "old-2"]
        );
        assert_eq!(rows(&root.join("vadgr.db"), "devices"), ["d-new", "d-old"]);
    }

    /// The journals travel with the database, because a run row whose
    /// trajectory is missing is a run nobody can resume or audit.
    #[test]
    fn the_journals_move_with_the_database() {
        let t = temp();
        let (root, cwd, home) = (t.join("root"), t.join("cwd"), t.join("home"));
        sqlite(
            &cwd.join("data").join("vadgr-rust.db"),
            &[("runs", &["r1"])],
        );
        let legacy = home.join(".vadgr").join("runs").join("r1");
        std::fs::create_dir_all(&legacy).unwrap();
        std::fs::write(legacy.join("trajectory.jsonl"), b"{\"a\":1}\n").unwrap();

        let inv = take_inventory(&root, &cwd, Some(&home));
        apply(&decide(&inv, &root).unwrap(), &root).unwrap();

        let moved = root.join("runs").join("r1").join("trajectory.jsonl");
        assert!(moved.exists(), "the journal did not move");
        assert_eq!(std::fs::read_to_string(moved).unwrap(), "{\"a\":1}\n");
    }

    /// A journal with no run row still moves. An orphan is evidence, and
    /// deleting evidence to tidy a directory is not a migration.
    #[test]
    fn an_orphan_journal_moves_rather_than_being_dropped() {
        let t = temp();
        let (root, cwd, home) = (t.join("root"), t.join("cwd"), t.join("home"));
        sqlite(
            &cwd.join("data").join("vadgr-rust.db"),
            &[("runs", &["r1"])],
        );
        let orphan = home.join(".vadgr").join("runs").join("no-such-run");
        std::fs::create_dir_all(&orphan).unwrap();
        std::fs::write(orphan.join("trajectory.jsonl"), b"x").unwrap();

        let inv = take_inventory(&root, &cwd, Some(&home));
        apply(&decide(&inv, &root).unwrap(), &root).unwrap();
        assert!(root.join("runs").join("no-such-run").exists());
    }

    /// **The commit is the rename.** A stage left by an interrupted attempt is
    /// debris: the next start discards it and the target is built again.
    #[test]
    fn an_interrupted_attempt_leaves_no_target_and_is_retried_cleanly() {
        let t = temp();
        let (root, cwd) = (t.join("root"), t.join("cwd"));
        sqlite(
            &cwd.join("data").join("vadgr-rust.db"),
            &[("runs", &["r1"])],
        );

        // What an interruption between stage and rename leaves behind.
        let stage = root.with_extension("staging");
        std::fs::create_dir_all(&stage).unwrap();
        std::fs::write(stage.join("vadgr.db"), b"half written").unwrap();
        assert!(!root.exists(), "an interruption leaves no target");

        let inv = take_inventory(&root, &cwd, None);
        apply(&decide(&inv, &root).unwrap(), &root).unwrap();
        assert_eq!(rows(&root.join("vadgr.db"), "runs"), ["r1"]);
        assert!(!stage.exists(), "the debris is gone");
    }

    /// The sources go only after the target is readable, so a failed move never
    /// leaves a machine with no history and no way back.
    #[test]
    fn the_sources_are_removed_only_after_the_target_verifies() {
        let t = temp();
        let (root, cwd) = (t.join("root"), t.join("cwd"));
        let source = cwd.join("data").join("vadgr-rust.db");
        sqlite(&source, &[("runs", &["r1"])]);
        let inv = take_inventory(&root, &cwd, None);
        apply(&decide(&inv, &root).unwrap(), &root).unwrap();
        assert!(root.join("vadgr.db").exists());
        assert!(
            !source.exists(),
            "the source is removed after the target verifies"
        );
    }

    /// A run committed to the write-ahead log and not yet checkpointed is still
    /// a run. Copying the `.db` alone drops it, which was found for real while
    /// assembling evidence during `0.4.7`.
    #[test]
    fn a_run_still_in_the_write_ahead_log_survives_the_move() {
        let t = temp();
        let (root, cwd) = (t.join("root"), t.join("cwd"));
        let source = cwd.join("data").join("vadgr-rust.db");
        std::fs::create_dir_all(source.parent().unwrap()).unwrap();
        let conn = Connection::open(&source).unwrap();
        conn.execute_batch(
            "PRAGMA journal_mode=WAL;
             CREATE TABLE runs (id TEXT PRIMARY KEY, title TEXT);
             INSERT INTO runs (id, title) VALUES ('in-wal', 'x');",
        )
        .unwrap();
        drop(conn);

        let inv = take_inventory(&root, &cwd, None);
        apply(&decide(&inv, &root).unwrap(), &root).unwrap();
        assert_eq!(rows(&root.join("vadgr.db"), "runs"), ["in-wal"]);
    }

    /// Every refusal says what to do, because one a person cannot act on is an
    /// outage rather than a safeguard.
    #[test]
    fn every_refusal_names_what_was_found_and_what_to_do() {
        let cases = [
            Refusal::RunIdInBoth {
                id: "r".into(),
                a: PathBuf::from("/a"),
                b: PathBuf::from("/b"),
            },
            Refusal::DeviceIdInBoth {
                id: "d".into(),
                a: PathBuf::from("/a"),
                b: PathBuf::from("/b"),
            },
            Refusal::TargetOccupied {
                root: PathBuf::from("/r"),
            },
            Refusal::Unreadable {
                path: PathBuf::from("/p"),
                reason: "locked".into(),
            },
        ];
        for case in cases {
            let text = case.to_string();
            assert!(
                text.contains("Nothing has been moved"),
                "a refusal must say the sources are untouched: {text}"
            );
        }
    }
}
