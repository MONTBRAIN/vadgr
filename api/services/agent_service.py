"""Agent service -- wraps repository + forge analysis."""

from api.persistence.repositories import AgentRepository


class AgentService:
    """Business logic for agent management. In future, calls forge to analyze
    descriptions and generate forge_config."""

    def __init__(self, agent_repo: AgentRepository):
        self.agent_repo = agent_repo

    async def analyze_and_create(self, name: str, description: str, **kwargs) -> dict:
        """Create an agent. In future, sends description to forge for analysis."""
        # MVP: forge analysis is stubbed. Returns simple config.
        forge_config = self._stub_forge_analysis(description)
        input_schema = kwargs.pop("input_schema", [])
        output_schema = kwargs.pop("output_schema", [])

        return await self.agent_repo.create(
            name=name,
            description=description,
            forge_config=forge_config,
            input_schema=input_schema,
            output_schema=output_schema,
            **kwargs,
        )

    def _stub_forge_analysis(self, description: str) -> dict:
        """Stub forge analysis. Will be replaced with real forge integration."""
        word_count = len(description.split())
        if word_count > 50:
            return {"complexity": "multi_step", "agents": 2, "steps": 3}
        return {"complexity": "simple", "agents": 1, "steps": 1}
