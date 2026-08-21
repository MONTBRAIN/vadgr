use anyhow::{Context, Result, bail};
use serde_json::{Map, Value, json};
use vadgr_daemon::computer_use_setup::SetupService;
use vadgr_daemon::config::Config;
use vadgr_daemon::db::Db;
use vadgr_daemon::engine::mcp::McpHost;
use vadgr_daemon::engine::mcp::cua::CuaServer;
use vadgr_daemon::engine::provider::ProviderService;
use vadgr_daemon::engine::{ContentBlock, Message, StopReason};

#[tokio::main]
async fn main() -> Result<()> {
    let config = Config::from_env().map_err(|e| anyhow::anyhow!("{e}"))?;
    let db = Db::open(&config.db_path)?;
    let providers = ProviderService::native(db, config.state_home.clone())?;
    let (provider, model_id) = providers
        .default_model()?
        .context("no default model is connected")?;
    let model = providers.build_client(&provider, &model_id)?;

    let entry = SetupService::from_env()?.entry()?;
    if !entry.enabled {
        bail!("computer use is disabled")
    }
    let command = entry.command.context("vadgr-cua was not found")?;
    let mut host = McpHost::new(vec![Box::new(CuaServer::new(command))]);
    host.connect().await?;
    let platform_tool = host
        .tools()
        .iter()
        .find(|tool| tool.name.ends_with("__get_platform"))
        .context("cua did not publish get_platform")?
        .name
        .clone();
    let prompt = format!(
        "Call the `{platform_tool}` tool exactly once with an empty object. Do not call another tool."
    );
    let response = model
        .complete(&[Message::text("user", prompt)], host.tools(), 1024)
        .await?;
    if response.stop_reason != Some(StopReason::ToolUse) {
        bail!("model did not return tool_use: {:?}", response.stop_reason)
    }
    let call = response
        .content
        .iter()
        .find_map(|block| match block {
            ContentBlock::ToolUse { name, input, .. } => Some((name.clone(), input.clone())),
            _ => None,
        })
        .context("model response did not contain a tool call")?;
    if call.0 != platform_tool {
        bail!("model selected `{}` instead of `{platform_tool}`", call.0)
    }
    let args = match call.1 {
        Value::Object(args) => args,
        _ => Map::new(),
    };
    let result = host.dispatch(&call.0, args).await?;
    host.close().await;
    if result.content.is_empty() {
        bail!("cua returned empty content")
    }
    if response.usage.input_tokens == 0 || response.usage.output_tokens == 0 {
        bail!("provider returned zero usage")
    }
    println!(
        "{}",
        json!({
            "provider": provider,
            "model": model_id,
            "tool": call.0,
            "result": result,
            "usage": response.usage,
        })
    );
    Ok(())
}
