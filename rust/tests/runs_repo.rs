//! The run repository and the wire mapping the shipped phone reads.

use serde_json::json;
use vadgr_daemon::db::{runs, Db};

fn seeded() -> Db {
    let db = Db::open(":memory:").unwrap();
    db.with(|c| {
        c.execute_batch(
            "INSERT INTO runs (id, title, status, inputs, outputs, provider, model, started_at)
               VALUES ('r1','triage-pull-requests','completed','{\"task\":\"t\"}','{\"result\":\"ok\"}','anthropic','claude-opus-5','2026-08-10T10:00:00');
             INSERT INTO runs (id, title, status) VALUES ('r2','clean up downloads','queued');",
        )
    })
    .unwrap();
    db
}

#[test]
fn the_wire_key_is_agent_name_and_it_carries_the_title() {
    // The deletion removed the agents table and backfilled the title from it,
    // and deliberately did not rename the key: the shipped phone reads
    // `agent_name`, and renaming it in the release that deleted its source
    // would have broken the app twice over.
    let db = seeded();
    let run = runs::get(&db, "r1").unwrap().unwrap();
    assert_eq!(run["agent_name"], "triage-pull-requests");
    assert!(run.get("title").is_none(), "the storage name never reaches the wire");
}

#[test]
fn json_columns_arrive_parsed_not_as_strings() {
    let db = seeded();
    let run = runs::get(&db, "r1").unwrap().unwrap();
    assert_eq!(run["inputs"], json!({"task": "t"}));
    assert_eq!(run["outputs"], json!({"result": "ok"}));
}

#[test]
fn a_queued_run_has_no_started_at_and_sorts_last() {
    // A queued run is a state, not a gap: it is drawn, and it sits nearest the
    // composer rather than being given a date nobody computed.
    let db = seeded();
    let all = runs::list_all(&db, None).unwrap();
    assert_eq!(all.len(), 2);
    assert_eq!(all[0]["id"], "r1");
    assert_eq!(all[1]["id"], "r2");
    assert!(all[1]["started_at"].is_null());
}

#[test]
fn the_status_filter_is_the_one_the_cli_sends() {
    let db = seeded();
    let failed = runs::list_all(&db, Some("failed")).unwrap();
    assert!(failed.is_empty());
    let queued = runs::list_all(&db, Some("queued")).unwrap();
    assert_eq!(queued.len(), 1);
    assert_eq!(queued[0]["id"], "r2");
}

#[test]
fn a_status_this_build_does_not_know_round_trips() {
    // Both daemons run against copies of the same database during the
    // migration, so a row written by the other one must survive a read here
    // rather than fail it. The column is free TEXT and this does not promote it.
    let db = seeded();
    db.with(|c| c.execute("UPDATE runs SET status = 'input_required' WHERE id = 'r2'", []))
        .unwrap();
    let run = runs::get(&db, "r2").unwrap().unwrap();
    assert_eq!(run["status"], "input_required");
}

#[test]
fn a_terminal_transition_stamps_completed_at_and_a_live_one_does_not() {
    let db = seeded();
    let updated = runs::update_status(&db, "r2", "running").unwrap().unwrap();
    assert!(updated["completed_at"].is_null());
    let updated = runs::update_status(&db, "r2", "failed").unwrap().unwrap();
    assert!(!updated["completed_at"].is_null());
}

#[test]
fn running_stamps_started_at_exactly_once() {
    // COALESCE, like the Python repository: a run that goes to `running`
    // again keeps when it first started rather than rewriting history.
    let db = seeded();
    let first = runs::update_status(&db, "r2", "running").unwrap().unwrap();
    let started = first["started_at"].as_str().unwrap().to_string();
    assert!(started.ends_with("+00:00"), "the Python timestamp shape: {started}");
    let again = runs::update_status(&db, "r2", "running").unwrap().unwrap();
    assert_eq!(again["started_at"], started.as_str());
}

#[test]
fn getting_a_run_that_is_not_there_is_none_not_an_error() {
    let db = seeded();
    assert!(runs::get(&db, "nope").unwrap().is_none());
}
