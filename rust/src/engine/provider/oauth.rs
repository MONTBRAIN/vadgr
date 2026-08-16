use crate::engine::types::ProviderError;
use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use rand::RngExt;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use time::{Duration, OffsetDateTime};
use url::Url;

const TOKEN_BODY_LIMIT: usize = 64 * 1024;

#[derive(Clone, Debug)]
pub struct OAuthDescriptor {
    pub authorize_url: &'static str,
    pub token_url: &'static str,
    pub client_id: &'static str,
    pub redirect_uri: &'static str,
    pub scopes: &'static [&'static str],
    pub authorize_parameters: &'static [(&'static str, &'static str)],
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PendingOAuth {
    pub authorization_url: String,
    pub verifier: String,
    pub state: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct OAuthTokens {
    pub access_token: String,
    pub refresh_token: Option<String>,
    pub expires_at: Option<String>,
}

#[derive(Deserialize)]
struct TokenResponse {
    access_token: String,
    #[serde(default)]
    refresh_token: Option<String>,
    #[serde(default)]
    expires_in: Option<i64>,
    #[serde(default)]
    expires_at: Option<String>,
    #[serde(default)]
    #[serde(rename = "token_type")]
    _token_type: Option<String>,
    #[serde(default)]
    #[serde(rename = "scope")]
    _scope: Option<String>,
    #[serde(default)]
    #[serde(rename = "id_token")]
    _id_token: Option<String>,
}

pub fn begin(descriptor: &OAuthDescriptor) -> Result<PendingOAuth, ProviderError> {
    let verifier = random_urlsafe(32);
    let state = random_urlsafe(16);
    let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()));
    let mut url = Url::parse(descriptor.authorize_url)
        .map_err(|error| ProviderError::InvalidResponse(error.to_string()))?;
    {
        let mut query = url.query_pairs_mut();
        query
            .append_pair("response_type", "code")
            .append_pair("client_id", descriptor.client_id)
            .append_pair("redirect_uri", descriptor.redirect_uri)
            .append_pair("scope", &descriptor.scopes.join(" "))
            .append_pair("code_challenge", &challenge)
            .append_pair("code_challenge_method", "S256")
            .append_pair("state", &state);
        for (key, value) in descriptor.authorize_parameters {
            query.append_pair(key, value);
        }
    }
    Ok(PendingOAuth {
        authorization_url: url.into(),
        verifier,
        state,
    })
}

pub fn validate_callback(expected_state: &str, received_state: &str) -> Result<(), ProviderError> {
    if expected_state.as_bytes() != received_state.as_bytes() {
        return Err(ProviderError::InvalidCredentials(
            "OAuth callback state does not match".to_owned(),
        ));
    }
    Ok(())
}

pub async fn exchange(
    http: &reqwest::Client,
    descriptor: &OAuthDescriptor,
    code: &str,
    verifier: &str,
) -> Result<OAuthTokens, ProviderError> {
    token_request(
        http,
        descriptor.token_url,
        &[
            ("grant_type", "authorization_code"),
            ("client_id", descriptor.client_id),
            ("code", code),
            ("code_verifier", verifier),
            ("redirect_uri", descriptor.redirect_uri),
        ],
        None,
    )
    .await
}

pub async fn refresh(
    http: &reqwest::Client,
    descriptor: &OAuthDescriptor,
    refresh_token: &str,
) -> Result<OAuthTokens, ProviderError> {
    token_request(
        http,
        descriptor.token_url,
        &[
            ("grant_type", "refresh_token"),
            ("client_id", descriptor.client_id),
            ("refresh_token", refresh_token),
        ],
        Some(refresh_token),
    )
    .await
}

async fn token_request(
    http: &reqwest::Client,
    token_url: &str,
    form: &[(&str, &str)],
    previous_refresh_token: Option<&str>,
) -> Result<OAuthTokens, ProviderError> {
    let response = http
        .post(token_url)
        .form(form)
        .send()
        .await
        .map_err(|error| ProviderError::Request(error.to_string()))?;
    let status = response.status();
    let bytes = super::read_bounded(response, TOKEN_BODY_LIMIT, "OAuth token response").await?;
    if status == reqwest::StatusCode::UNAUTHORIZED {
        return Err(ProviderError::Unauthorized);
    }
    if !status.is_success() {
        return Err(ProviderError::Request(format!(
            "OAuth token request failed with HTTP {}",
            status.as_u16()
        )));
    }
    let body: TokenResponse = serde_json::from_slice(&bytes)
        .map_err(|error| ProviderError::InvalidResponse(error.to_string()))?;
    if body.access_token.trim().is_empty() {
        return Err(ProviderError::InvalidResponse(
            "OAuth token response has no access token".to_owned(),
        ));
    }
    let expires_at = match (body.expires_at, body.expires_in) {
        (Some(value), _) => Some(value),
        (None, Some(seconds)) if seconds > 0 => Some(
            (OffsetDateTime::now_utc() + Duration::seconds(seconds))
                .format(&time::format_description::well_known::Rfc3339)
                .expect("a timestamp always formats"),
        ),
        _ => None,
    };
    Ok(OAuthTokens {
        access_token: body.access_token,
        refresh_token: body
            .refresh_token
            .or_else(|| previous_refresh_token.map(str::to_owned)),
        expires_at,
    })
}

fn random_urlsafe(bytes: usize) -> String {
    let mut rng = rand::rng();
    let value = (0..bytes).map(|_| rng.random::<u8>()).collect::<Vec<_>>();
    URL_SAFE_NO_PAD.encode(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    const DESCRIPTOR: OAuthDescriptor = OAuthDescriptor {
        authorize_url: "https://auth.example/authorize",
        token_url: "https://auth.example/token",
        client_id: "public-client",
        redirect_uri: "http://localhost:1455/auth/callback",
        scopes: &["openid", "offline_access"],
        authorize_parameters: &[("originator", "vadgr")],
    };

    #[test]
    fn begin_creates_pkce_state_and_provider_parameters() {
        let pending = begin(&DESCRIPTOR).unwrap();
        let url = Url::parse(&pending.authorization_url).unwrap();
        let query = url
            .query_pairs()
            .collect::<std::collections::HashMap<_, _>>();
        assert_eq!(
            query.get("client_id").map(|value| value.as_ref()),
            Some("public-client")
        );
        assert_eq!(
            query.get("redirect_uri").map(|value| value.as_ref()),
            Some(DESCRIPTOR.redirect_uri)
        );
        assert_eq!(
            query
                .get("code_challenge_method")
                .map(|value| value.as_ref()),
            Some("S256")
        );
        assert_eq!(
            query.get("originator").map(|value| value.as_ref()),
            Some("vadgr")
        );
        assert_eq!(
            query.get("state").map(|value| value.as_ref()),
            Some(pending.state.as_str())
        );
        assert_ne!(pending.verifier, pending.state);
    }

    #[test]
    fn callback_state_must_match_exactly() {
        assert!(validate_callback("expected", "expected").is_ok());
        assert!(validate_callback("expected", "wrong").is_err());
    }
}
