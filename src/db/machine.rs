//! The machine configuration store used by the API, CLI and native console.

use super::Db;
use anyhow::{Context, Result, anyhow};
use rusqlite::params;
use serde::{Deserialize, Serialize};

pub const DEFAULT_ROLE_PROMPT: &str = "Prefer the smallest action that finishes the job.";

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct MachineSettings {
    pub id: String,
    pub name: String,
    pub role_prompt: String,
    pub autonomy_mode: String,
    pub workspace: Option<String>,
    pub granted_skills: Vec<String>,
    pub granted_mcp_servers: Vec<String>,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct MachinePatch {
    pub name: Option<String>,
    pub role_prompt: Option<Option<String>>,
    pub autonomy_mode: Option<String>,
    pub workspace: Option<Option<String>>,
    pub granted_skills: Option<Vec<String>>,
    pub granted_mcp_servers: Option<Vec<String>>,
}

pub fn get(db: &Db) -> Result<MachineSettings> {
    ensure_identity(db)?;
    db.with(|conn| {
        conn.query_row(
            "SELECT machine_id, name, role_prompt, autonomy_mode, workspace,
                    granted_skills, granted_mcp_servers
             FROM machine_settings WHERE id=1",
            [],
            |row| {
                let skills: String = row.get(5)?;
                let servers: String = row.get(6)?;
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, Option<String>>(4)?,
                    skills,
                    servers,
                ))
            },
        )
    })
    .context("reading machine settings")
    .and_then(
        |(id, name, role_prompt, autonomy_mode, workspace, skills, servers)| {
            Ok(MachineSettings {
                id,
                name,
                role_prompt,
                autonomy_mode,
                workspace,
                granted_skills: serde_json::from_str(&skills).context("reading skill grants")?,
                granted_mcp_servers: serde_json::from_str(&servers)
                    .context("reading MCP server grants")?,
            })
        },
    )
}

pub fn update(db: &Db, patch: &MachinePatch) -> Result<MachineSettings> {
    validate(patch)?;
    let current = get(db)?;
    let name = patch.name.as_ref().unwrap_or(&current.name);
    let role_prompt = patch
        .role_prompt
        .as_ref()
        .map(|value| value.as_deref().unwrap_or(DEFAULT_ROLE_PROMPT))
        .unwrap_or(&current.role_prompt);
    let autonomy_mode = patch
        .autonomy_mode
        .as_ref()
        .unwrap_or(&current.autonomy_mode);
    let workspace = patch.workspace.as_ref().unwrap_or(&current.workspace);
    let skills = patch
        .granted_skills
        .as_ref()
        .unwrap_or(&current.granted_skills);
    let servers = patch
        .granted_mcp_servers
        .as_ref()
        .unwrap_or(&current.granted_mcp_servers);
    db.with(|conn| {
        conn.execute(
            "UPDATE machine_settings SET name=?1, role_prompt=?2, autonomy_mode=?3,
                    workspace=?4, granted_skills=?5, granted_mcp_servers=?6 WHERE id=1",
            params![
                name,
                role_prompt,
                autonomy_mode,
                workspace,
                serde_json::to_string(skills).expect("string arrays serialize"),
                serde_json::to_string(servers).expect("string arrays serialize"),
            ],
        )?;
        Ok(())
    })
    .context("writing machine settings")?;
    get(db)
}

fn ensure_identity(db: &Db) -> Result<()> {
    db.with(|conn| {
        let current: (String, String, String) = conn.query_row(
            "SELECT machine_id, name, role_prompt FROM machine_settings WHERE id=1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )?;
        let id = if current.0.is_empty() {
            format!("m-{}", &uuid::Uuid::new_v4().simple().to_string()[..6])
        } else {
            current.0
        };
        let name = if current.1.is_empty() {
            hostname::get()
                .ok()
                .and_then(|value| value.into_string().ok())
                .filter(|value| !value.trim().is_empty())
                .unwrap_or_else(|| "This machine".to_owned())
        } else {
            current.1
        };
        let role = if current.2.is_empty() {
            DEFAULT_ROLE_PROMPT.to_owned()
        } else {
            current.2
        };
        conn.execute(
            "UPDATE machine_settings SET machine_id=?1, name=?2, role_prompt=?3 WHERE id=1",
            params![id, name, role],
        )?;
        Ok(())
    })
    .context("initializing machine identity")
}

pub fn validate(patch: &MachinePatch) -> Result<()> {
    if patch
        .name
        .as_ref()
        .is_some_and(|value| value.trim().is_empty())
    {
        return Err(anyhow!("name must not be empty"));
    }
    if let Some(mode) = &patch.autonomy_mode
        && !matches!(
            mode.as_str(),
            "bypass" | "default" | "autonomous" | "paranoid"
        )
    {
        return Err(anyhow!("autonomy.mode is not supported"));
    }
    if let Some(Some(path)) = &patch.workspace
        && !std::path::Path::new(path).is_absolute()
    {
        return Err(anyhow!("workspace must be absolute or null"));
    }
    if patch.granted_mcp_servers.as_ref().is_some_and(|values| {
        !values.iter().any(|value| value == "control-plane")
            || !values.iter().any(|value| value == "vadgr-computer-use")
    }) {
        return Err(anyhow!("required MCP servers cannot be removed"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identity_is_stable_and_patch_updates_one_store() {
        let db = Db::open(":memory:").unwrap();
        let first = get(&db).unwrap();
        let changed = update(
            &db,
            &MachinePatch {
                name: Some("Studio workstation".to_owned()),
                autonomy_mode: Some("paranoid".to_owned()),
                ..Default::default()
            },
        )
        .unwrap();
        assert_eq!(changed.id, first.id);
        assert_eq!(changed.name, "Studio workstation");
        assert_eq!(get(&db).unwrap(), changed);
    }

    #[test]
    fn invalid_edits_leave_the_row_unchanged() {
        let db = Db::open(":memory:").unwrap();
        let before = get(&db).unwrap();
        assert!(
            update(
                &db,
                &MachinePatch {
                    workspace: Some(Some("relative".to_owned())),
                    ..Default::default()
                }
            )
            .is_err()
        );
        assert_eq!(get(&db).unwrap(), before);
    }
}
