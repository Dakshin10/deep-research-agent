from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.sandbox.client import SandboxClient, LocalSubprocessSandboxClient, SandboxResult
from core.state.store import StateStore
from core.state.schemas import Artifact, ResearchNote, EventType


class ExecutionResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    script_artifact: Optional[Artifact] = None
    output_artifacts: List[Artifact] = Field(default_factory=list)
    computed_notes: List[ResearchNote] = Field(default_factory=list)


class ExecuteToolService:
    """Executes computation skills in the sandbox, persisting scripts, output files, and computed notes."""

    def __init__(
        self,
        tenant_id: str,
        state_store: StateStore,
        sandbox_client: Optional[SandboxClient] = None,
    ):
        self.tenant_id = tenant_id
        self.state_store = state_store
        self.sandbox = sandbox_client or LocalSubprocessSandboxClient()

    async def execute_computation(
        self,
        job_id: str,
        script_title: str,
        code: str,
        input_files: Optional[Dict[str, bytes]] = None,
        task_id: str = "computation",
    ) -> ExecutionResponse:
        input_files = input_files or {}

        # 1. Execute in sandbox
        await self.state_store.emit_event(
            job_id,
            EventType.TOOL_CALL,
            {"tool": "execute_tool", "script": script_title, "task_id": task_id},
        )
        res: SandboxResult = await self.sandbox.aexecute(code=code, files=input_files)

        # 2. Store generated script as an Artifact
        script_artifact = Artifact(
            id=f"art_script_{uuid.uuid4().hex[:6]}",
            job_id=job_id,
            tenant_id=self.tenant_id,
            artifact_type="script",
            title=f"Computation Script: {script_title}",
            content=code,
            metadata={"exit_code": res.exit_code, "execution_time": res.execution_time},
        )
        await self.state_store.add_artifact(script_artifact)

        output_artifacts: List[Artifact] = []
        computed_notes: List[ResearchNote] = []

        if res.exit_code != 0:
            return ExecutionResponse(
                success=False,
                stdout=res.stdout,
                stderr=res.stderr,
                script_artifact=script_artifact,
            )

        # 3. Store output files (e.g. chart.png, summary.json) as Artifacts
        for fname, content in res.output_files.items():
            atype = "chart" if fname.endswith((".png", ".jpg", ".svg")) else "data"
            art = Artifact(
                id=f"art_{uuid.uuid4().hex[:6]}",
                job_id=job_id,
                tenant_id=self.tenant_id,
                artifact_type=atype,
                title=f"Output File: {fname}",
                file_path=fname,
                metadata={"size_bytes": len(content), "script_id": script_artifact.id},
            )
            await self.state_store.add_artifact(art)
            output_artifacts.append(art)

            # Check if this output file is JSON with computed metrics
            if fname.endswith(".json"):
                try:
                    data = json.loads(content.decode("utf-8"))
                    if isinstance(data, dict):
                        for k, v in data.items():
                            note = ResearchNote(
                                id=f"note_calc_{uuid.uuid4().hex[:6]}",
                                job_id=job_id,
                                tenant_id=self.tenant_id,
                                claim=f"Computed {k}: {v}",
                                source_type="computed",
                                document_id=art.id,
                                excerpt=f"Deterministically computed in sandbox script '{script_title}': {k} = {v}",
                                confidence=1.0,
                                task_id=task_id,
                            )
                            await self.state_store.add_note(note)
                            computed_notes.append(note)
                except Exception:
                    pass

        # 4. If stdout contains JSON, also extract computed values
        if not computed_notes and res.stdout.strip().startswith("{") and res.stdout.strip().endswith("}"):
            try:
                data = json.loads(res.stdout.strip())
                if isinstance(data, dict):
                    for k, v in data.items():
                        note = ResearchNote(
                            id=f"note_calc_{uuid.uuid4().hex[:6]}",
                            job_id=job_id,
                            tenant_id=self.tenant_id,
                            claim=f"Computed {k}: {v}",
                            source_type="computed",
                            document_id=script_artifact.id,
                            excerpt=f"Deterministically computed: {k} = {v}",
                            confidence=1.0,
                            task_id=task_id,
                        )
                        await self.state_store.add_note(note)
                        computed_notes.append(note)
            except Exception:
                pass

        return ExecutionResponse(
            success=True,
            stdout=res.stdout,
            stderr=res.stderr,
            script_artifact=script_artifact,
            output_artifacts=output_artifacts,
            computed_notes=computed_notes,
        )
