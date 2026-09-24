use super::{Db, now_iso};
use anyhow::{Result, anyhow};
use rusqlite::types::Type;
use rusqlite::{OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashSet;
use time::{Duration, OffsetDateTime};

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct ProviderModel {
    pub id: String,
    pub name: String,
    #[serde(default = "default_capabilities")]
    pub capabilities: Value,
}

fn default_capabilities() -> Value {
    json!({"text":true,"tools":true})
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Connection {
    pub provider_id: String,
    pub auth_method: String,
    pub secret_ref: String,
    pub account_id: Option<String>,
    pub credential_expires_at: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Catalog {
    pub verified_at: String,
    pub expires_at: String,
    pub models: Vec<ProviderModel>,
}

#[derive(Clone, Debug)]
pub struct ConnectionCommit {
    pub connection: Connection,
    pub models: Vec<ProviderModel>,
    pub default_model: Option<String>,
}

pub fn connections(db: &Db) -> Result<Vec<Connection>> {
    db.with(|conn| {
        let mut statement = conn.prepare(
            "SELECT provider_id, auth_method, secret_ref, account_id, credential_expires_at
             FROM provider_connections ORDER BY provider_id",
        )?;
        statement
            .query_map([], |row| {
                Ok(Connection {
                    provider_id: row.get(0)?,
                    auth_method: row.get(1)?,
                    secret_ref: row.get(2)?,
                    account_id: row.get(3)?,
                    credential_expires_at: row.get(4)?,
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()
    })
    .map_err(Into::into)
}

pub fn referenced_secrets(db: &Db) -> Result<HashSet<String>> {
    Ok(connections(db)?
        .into_iter()
        .map(|connection| connection.secret_ref)
        .collect())
}

pub fn default_model(db: &Db) -> Result<Option<(String, String)>> {
    db.with(|conn| {
        conn.query_row(
            "SELECT default_provider, default_model FROM machine_settings WHERE id = 1",
            [],
            |row| {
                Ok((
                    row.get::<_, Option<String>>(0)?,
                    row.get::<_, Option<String>>(1)?,
                ))
            },
        )
    })
    .map(|(provider, model)| provider.zip(model))
    .map_err(Into::into)
}

/// Restore the machine default after a larger configuration write fails.
pub fn restore_default(db: &Db, value: Option<(&str, &str)>) -> Result<()> {
    Ok(db.with(|conn| {
        let (provider, model) = value
            .map(|(provider, model)| (Some(provider), Some(model)))
            .unwrap_or((None, None));
        conn.execute(
            "UPDATE machine_settings SET default_provider=?1, default_model=?2 WHERE id=1",
            params![provider, model],
        )?;
        Ok(())
    })?)
}

pub fn connection(db: &Db, provider_id: &str) -> Result<Option<Connection>> {
    db.with(|conn| {
        conn.query_row(
            "SELECT provider_id, auth_method, secret_ref, account_id, credential_expires_at
             FROM provider_connections WHERE provider_id = ?1",
            [provider_id],
            |row| {
                Ok(Connection {
                    provider_id: row.get(0)?,
                    auth_method: row.get(1)?,
                    secret_ref: row.get(2)?,
                    account_id: row.get(3)?,
                    credential_expires_at: row.get(4)?,
                })
            },
        )
        .optional()
    })
    .map_err(Into::into)
}

pub fn catalog(db: &Db, provider_id: &str) -> Result<Option<Catalog>> {
    db.with(|conn| {
        let times = conn
            .query_row(
                "SELECT verified_at, expires_at FROM provider_catalogs WHERE provider_id = ?1",
                [provider_id],
                |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
            )
            .optional()?;
        let Some((verified_at, expires_at)) = times else {
            return Ok(None);
        };
        let mut statement = conn.prepare(
            "SELECT model_id, name, capabilities FROM provider_models
             WHERE provider_id = ?1 ORDER BY model_id",
        )?;
        let models = statement
            .query_map([provider_id], |row| {
                let capabilities: String = row.get(2)?;
                Ok(ProviderModel {
                    id: row.get(0)?,
                    name: row.get(1)?,
                    capabilities: serde_json::from_str(&capabilities).map_err(|error| {
                        rusqlite::Error::FromSqlConversionFailure(2, Type::Text, Box::new(error))
                    })?,
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(Some(Catalog {
            verified_at,
            expires_at,
            models,
        }))
    })
    .map_err(Into::into)
}

pub fn commit_connection(db: &Db, value: &ConnectionCommit) -> Result<Option<String>> {
    if value.models.is_empty() {
        return Err(anyhow!("provider catalog is empty"));
    }
    if let Some(model) = &value.default_model
        && !value.models.iter().any(|candidate| &candidate.id == model)
    {
        return Err(anyhow!("default model is not in the provider catalog"));
    }

    db.with_mut(|conn| {
        let tx = conn.transaction()?;
        let old_ref = tx
            .query_row(
                "SELECT secret_ref FROM provider_connections WHERE provider_id = ?1",
                [&value.connection.provider_id],
                |row| row.get::<_, String>(0),
            )
            .optional()?;
        let now = now_iso();
        let expires = (OffsetDateTime::now_utc() + Duration::hours(24))
            .format(&time::format_description::well_known::Rfc3339)
            .expect("a timestamp always formats");
        let current_default = tx.query_row(
            "SELECT default_provider, default_model FROM machine_settings WHERE id=1",
            [],
            |row| {
                Ok((
                    row.get::<_, Option<String>>(0)?,
                    row.get::<_, Option<String>>(1)?,
                ))
            },
        )?;
        let current_default = current_default.0.zip(current_default.1);
        let requested_default = match &current_default {
            None => Some(value.default_model.as_ref().ok_or(
                rusqlite::Error::InvalidParameterName(
                    "the first connection requires a default model".to_owned(),
                ),
            )?),
            Some((provider, current_model)) if provider == &value.connection.provider_id => {
                let selected = value.default_model.as_ref().unwrap_or(current_model);
                if !value
                    .models
                    .iter()
                    .any(|candidate| &candidate.id == selected)
                {
                    return Err(rusqlite::Error::InvalidParameterName(
                        "the replacement credential cannot use the current default model"
                            .to_owned(),
                    ));
                }
                Some(selected)
            }
            Some(_) => None,
        };

        tx.execute(
            "INSERT INTO provider_connections
             (provider_id, auth_method, secret_ref, account_id, credential_expires_at, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)
             ON CONFLICT(provider_id) DO UPDATE SET
               auth_method=excluded.auth_method, secret_ref=excluded.secret_ref,
               account_id=excluded.account_id,
               credential_expires_at=excluded.credential_expires_at,
               updated_at=excluded.updated_at",
            params![
                value.connection.provider_id,
                value.connection.auth_method,
                value.connection.secret_ref,
                value.connection.account_id,
                value.connection.credential_expires_at,
                now,
            ],
        )?;
        tx.execute(
            "INSERT INTO provider_catalogs (provider_id, verified_at, expires_at)
             VALUES (?1, ?2, ?3)
             ON CONFLICT(provider_id) DO UPDATE SET
               verified_at=excluded.verified_at, expires_at=excluded.expires_at",
            params![value.connection.provider_id, now, expires],
        )?;
        for model in &value.models {
            tx.execute(
                "INSERT INTO provider_models
                 (provider_id, model_id, name, capabilities) VALUES (?1, ?2, ?3, ?4)
                 ON CONFLICT(provider_id, model_id) DO UPDATE SET
                   name=excluded.name, capabilities=excluded.capabilities",
                params![
                    value.connection.provider_id,
                    model.id,
                    model.name,
                    model.capabilities.to_string(),
                ],
            )?;
        }
        if let Some(model) = requested_default {
            tx.execute(
                "UPDATE machine_settings SET default_provider=?1, default_model=?2 WHERE id=1",
                params![value.connection.provider_id, model],
            )?;
        }
        remove_obsolete_models(&tx, &value.connection.provider_id, &value.models)?;
        tx.commit()?;
        Ok(old_ref.filter(|old| old != &value.connection.secret_ref))
    })
    .map_err(Into::into)
}

pub fn replace_catalog(db: &Db, provider_id: &str, models: &[ProviderModel]) -> Result<()> {
    if models.is_empty() {
        return Err(anyhow!("provider catalog is empty"));
    }
    db.with_mut(|conn| {
        let tx = conn.transaction()?;
        let current_default = tx
            .query_row(
                "SELECT default_model FROM machine_settings WHERE id=1 AND default_provider=?1",
                [provider_id],
                |row| row.get::<_, String>(0),
            )
            .optional()?;
        if current_default
            .as_ref()
            .is_some_and(|current| !models.iter().any(|model| &model.id == current))
        {
            return Err(rusqlite::Error::InvalidParameterName(
                "the refreshed catalog does not contain the machine default".to_owned(),
            ));
        }
        write_catalog(&tx, provider_id, models)?;
        tx.commit()
    })
    .map_err(Into::into)
}

pub fn replace_catalog_and_set_default(
    db: &Db,
    provider_id: &str,
    models: &[ProviderModel],
    model_id: &str,
) -> Result<()> {
    if models.is_empty() || !models.iter().any(|model| model.id == model_id) {
        return Err(anyhow!("default model is not in the provider catalog"));
    }
    db.with_mut(|conn| {
        let tx = conn.transaction()?;
        write_catalog(&tx, provider_id, models)?;
        if tx.execute(
            "UPDATE machine_settings SET default_provider=?1, default_model=?2 WHERE id=1",
            params![provider_id, model_id],
        )? != 1
        {
            return Err(rusqlite::Error::QueryReturnedNoRows);
        }
        tx.commit()
    })
    .map_err(Into::into)
}

pub fn model_exists(db: &Db, provider_id: &str, model_id: &str) -> Result<bool> {
    db.with(|conn| {
        conn.query_row(
            "SELECT EXISTS(
                SELECT 1 FROM provider_models WHERE provider_id=?1 AND model_id=?2
             )",
            params![provider_id, model_id],
            |row| row.get(0),
        )
    })
    .map_err(Into::into)
}

pub fn replace_secret_reference(
    db: &Db,
    provider_id: &str,
    old_reference: &str,
    new_reference: &str,
    expires_at: Option<&str>,
) -> Result<bool> {
    db.with(|conn| {
        Ok(conn.execute(
            "UPDATE provider_connections
             SET secret_ref=?3, credential_expires_at=?4, updated_at=?5
             WHERE provider_id=?1 AND secret_ref=?2",
            params![
                provider_id,
                old_reference,
                new_reference,
                expires_at,
                now_iso()
            ],
        )? == 1)
    })
    .map_err(Into::into)
}

pub fn delete_connection(db: &Db, provider_id: &str) -> Result<Option<String>> {
    if default_model(db)?.is_some_and(|(provider, _)| provider == provider_id) {
        return Err(anyhow!("the default provider cannot be disconnected"));
    }
    db.with(|conn| {
        let secret_ref = conn
            .query_row(
                "SELECT secret_ref FROM provider_connections WHERE provider_id=?1",
                [provider_id],
                |row| row.get::<_, String>(0),
            )
            .optional()?;
        conn.execute(
            "DELETE FROM provider_connections WHERE provider_id=?1",
            [provider_id],
        )?;
        Ok(secret_ref)
    })
    .map_err(Into::into)
}

fn remove_obsolete_models(
    tx: &rusqlite::Transaction<'_>,
    provider_id: &str,
    models: &[ProviderModel],
) -> rusqlite::Result<()> {
    let retained: HashSet<&str> = models.iter().map(|model| model.id.as_str()).collect();
    let existing = {
        let mut statement =
            tx.prepare("SELECT model_id FROM provider_models WHERE provider_id=?1")?;
        statement
            .query_map([provider_id], |row| row.get::<_, String>(0))?
            .collect::<rusqlite::Result<Vec<_>>>()?
    };
    for model_id in existing {
        if !retained.contains(model_id.as_str()) {
            tx.execute(
                "DELETE FROM provider_models WHERE provider_id=?1 AND model_id=?2",
                params![provider_id, model_id],
            )?;
        }
    }
    Ok(())
}

fn write_catalog(
    tx: &rusqlite::Transaction<'_>,
    provider_id: &str,
    models: &[ProviderModel],
) -> rusqlite::Result<()> {
    let now = now_iso();
    let expires = (OffsetDateTime::now_utc() + Duration::hours(24))
        .format(&time::format_description::well_known::Rfc3339)
        .expect("a timestamp always formats");
    if tx.execute(
        "UPDATE provider_catalogs SET verified_at=?2, expires_at=?3 WHERE provider_id=?1",
        params![provider_id, now, expires],
    )? != 1
    {
        return Err(rusqlite::Error::QueryReturnedNoRows);
    }
    for model in models {
        tx.execute(
            "INSERT INTO provider_models (provider_id, model_id, name, capabilities)
             VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT(provider_id, model_id) DO UPDATE SET
               name=excluded.name, capabilities=excluded.capabilities",
            params![
                provider_id,
                model.id,
                model.name,
                model.capabilities.to_string()
            ],
        )?;
    }
    remove_obsolete_models(tx, provider_id, models)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn candidate(provider: &str, reference: &str, model: &str) -> ConnectionCommit {
        ConnectionCommit {
            connection: Connection {
                provider_id: provider.to_owned(),
                auth_method: "api_key".to_owned(),
                secret_ref: reference.to_owned(),
                account_id: None,
                credential_expires_at: None,
            },
            models: vec![ProviderModel {
                id: model.to_owned(),
                name: model.to_owned(),
                capabilities: default_capabilities(),
            }],
            default_model: Some(model.to_owned()),
        }
    }

    #[test]
    fn connections_are_additive_and_later_login_preserves_default() {
        let db = Db::open(":memory:").unwrap();
        commit_connection(&db, &candidate("openai", "one", "gpt-test")).unwrap();
        commit_connection(&db, &candidate("gemini", "two", "gemini-test")).unwrap();
        assert_eq!(
            default_model(&db).unwrap(),
            Some(("openai".to_owned(), "gpt-test".to_owned()))
        );
        assert!(connection(&db, "openai").unwrap().is_some());
        assert!(connection(&db, "gemini").unwrap().is_some());
    }

    #[test]
    fn replacing_one_provider_returns_only_its_old_reference() {
        let db = Db::open(":memory:").unwrap();
        commit_connection(&db, &candidate("openai", "one", "gpt-test")).unwrap();
        let old = commit_connection(&db, &candidate("openai", "new", "gpt-test")).unwrap();
        assert_eq!(old.as_deref(), Some("one"));
    }

    #[test]
    fn the_default_provider_cannot_be_deleted() {
        let db = Db::open(":memory:").unwrap();
        commit_connection(&db, &candidate("openai", "one", "gpt-test")).unwrap();
        assert!(
            delete_connection(&db, "openai")
                .unwrap_err()
                .to_string()
                .contains("default")
        );
    }

    #[test]
    fn a_failed_default_provider_replacement_leaves_every_old_row_intact() {
        let db = Db::open(":memory:").unwrap();
        commit_connection(&db, &candidate("openai", "one", "gpt-old")).unwrap();
        let replacement = ConnectionCommit {
            connection: Connection {
                provider_id: "openai".to_owned(),
                auth_method: "oauth".to_owned(),
                secret_ref: "two".to_owned(),
                account_id: Some("account".to_owned()),
                credential_expires_at: None,
            },
            models: vec![ProviderModel {
                id: "gpt-new".to_owned(),
                name: "GPT New".to_owned(),
                capabilities: default_capabilities(),
            }],
            default_model: None,
        };

        assert!(commit_connection(&db, &replacement).is_err());

        assert_eq!(
            connection(&db, "openai").unwrap().unwrap().secret_ref,
            "one"
        );
        assert_eq!(
            catalog(&db, "openai").unwrap().unwrap().models[0].id,
            "gpt-old"
        );
        assert_eq!(
            default_model(&db).unwrap(),
            Some(("openai".to_owned(), "gpt-old".to_owned()))
        );
    }

    #[test]
    fn duplicate_secret_references_roll_back_the_second_connection() {
        let db = Db::open(":memory:").unwrap();
        commit_connection(&db, &candidate("openai", "shared", "gpt-test")).unwrap();

        assert!(commit_connection(&db, &candidate("gemini", "shared", "gemini-test")).is_err());
        assert!(connection(&db, "gemini").unwrap().is_none());
        assert!(catalog(&db, "gemini").unwrap().is_none());
        assert_eq!(
            default_model(&db).unwrap(),
            Some(("openai".to_owned(), "gpt-test".to_owned()))
        );
    }

    #[test]
    fn catalog_and_default_switch_commit_together() {
        let db = Db::open(":memory:").unwrap();
        commit_connection(&db, &candidate("openai", "one", "gpt-test")).unwrap();
        commit_connection(&db, &candidate("gemini", "two", "gemini-old")).unwrap();
        let new_models = vec![ProviderModel {
            id: "gemini-new".to_owned(),
            name: "Gemini New".to_owned(),
            capabilities: default_capabilities(),
        }];

        replace_catalog_and_set_default(&db, "gemini", &new_models, "gemini-new").unwrap();

        assert_eq!(
            default_model(&db).unwrap(),
            Some(("gemini".to_owned(), "gemini-new".to_owned()))
        );
        assert_eq!(catalog(&db, "gemini").unwrap().unwrap().models, new_models);
    }

    #[test]
    fn corrupt_catalog_capabilities_fail_closed() {
        let db = Db::open(":memory:").unwrap();
        commit_connection(&db, &candidate("openai", "one", "gpt-test")).unwrap();
        db.with(|conn| {
            conn.execute(
                "UPDATE provider_models SET capabilities='not-json' WHERE provider_id='openai'",
                [],
            )
        })
        .unwrap();

        assert!(catalog(&db, "openai").is_err());
    }
}
