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
        if request.risk.eq_ignore_ascii_case("high") {
            Decision::NeedsHuman {
                reason: "high-risk action".to_owned(),
            }
        } else {
            Decision::AutoAllow {
                reason: format!("default mode, risk={}", request.risk),
            }
        }
    }
}
