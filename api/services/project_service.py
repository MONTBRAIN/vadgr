"""Project service -- wraps repository + DAG validation."""

from api.engine.dag import DAG
from api.persistence.repositories import ProjectRepository


class ProjectService:
    """Business logic for project management."""

    def __init__(self, project_repo: ProjectRepository):
        self.project_repo = project_repo

    async def validate(self, project_id: str) -> dict:
        """Validate a project's DAG."""
        nodes = await self.project_repo.get_nodes(project_id)
        edges = await self.project_repo.get_edges(project_id)
        dag = DAG(nodes=nodes, edges=edges)
        errors = dag.validate()
        return {"valid": len(errors) == 0, "errors": errors}
