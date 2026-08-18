use async_trait::async_trait;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Decision {
    AutoAllow { reason: String },
    AutoDeny { reason: String },
    NeedsHuman { reason: String },
}

pub struct ApprovalRequest<'a> {
    pub action: &'a str,
    pub risk: &'a str,
}

#[async_trait]
pub trait PolicyHook: Send + Sync {
    async fn check(&self, request: ApprovalRequest<'_>) -> Decision;
}

#[derive(Default)]
pub struct DefaultPolicy {
    denylist: Vec<String>,
}

impl DefaultPolicy {
    pub fn new(denylist: Vec<String>) -> Self {
        Self { denylist }
    }
}

#[async_trait]
impl PolicyHook for DefaultPolicy {
    async fn check(&self, request: ApprovalRequest<'_>) -> Decision {
        if let Some(pattern) = self
            .denylist
            .iter()
            .find(|pattern| request.action.contains(pattern.as_str()))
        {
            return Decision::AutoDeny {
                reason: format!("denylisted: {pattern}"),
            };
        }
        // An approval gate must fail closed. `risk` crosses the wire as a
        // string the model fills in, and a model asked for the "risk" of an
        // action readily writes a sentence describing it rather than a
        // severity. Treating anything unrecognised as low risk auto-approved
        // the destructive actions the gate exists to stop, so only the two
        // known-safe severities may skip the owner.
        match request.risk.trim().to_ascii_lowercase().as_str() {
            "low" | "medium" => Decision::AutoAllow {
                reason: format!("default mode, risk={}", request.risk),
            },
            "high" => Decision::NeedsHuman {
                reason: "high-risk action".to_owned(),
            },
            _ => Decision::NeedsHuman {
                reason: format!("unrecognised risk {:?}; asking the owner", request.risk),
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn decide(risk: &str) -> Decision {
        tokio::runtime::Runtime::new()
            .unwrap()
            .block_on(DefaultPolicy::new(vec![]).check(ApprovalRequest {
                action: "delete one file",
                risk,
            }))
    }

    #[test]
    fn the_two_safe_severities_are_auto_allowed() {
        assert!(matches!(decide("low"), Decision::AutoAllow { .. }));
        assert!(matches!(decide("medium"), Decision::AutoAllow { .. }));
        assert!(matches!(decide("MEDIUM"), Decision::AutoAllow { .. }));
    }

    #[test]
    fn high_risk_asks_the_owner() {
        assert!(matches!(decide("high"), Decision::NeedsHuman { .. }));
    }

    /// The gate must fail closed. A model asked for the "risk" of an action
    /// writes prose as readily as a severity, and treating that as low risk
    /// auto-approved exactly the actions the gate exists to stop.
    #[test]
    fn an_unrecognised_risk_asks_the_owner_rather_than_allowing_it() {
        assert!(matches!(decide(""), Decision::NeedsHuman { .. }));
        assert!(matches!(decide("critical"), Decision::NeedsHuman { .. }));
        assert!(matches!(
            decide("This permanently removes the file from disk."),
            Decision::NeedsHuman { .. }
        ));
    }

    #[test]
    fn the_denylist_still_wins_over_every_severity() {
        let policy = DefaultPolicy::new(vec!["rm -rf".to_owned()]);
        let decision = tokio::runtime::Runtime::new()
            .unwrap()
            .block_on(policy.check(ApprovalRequest {
                action: "run rm -rf /",
                risk: "low",
            }));
        assert!(matches!(decision, Decision::AutoDeny { .. }));
    }
}
