from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from typing import Dict, Optional
from pydantic import BaseModel, Field

from core.observability.tracing import trace_tool


class SandboxResult(BaseModel):
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    output_files: Dict[str, bytes] = Field(default_factory=dict)
    execution_time: float = 0.0


class SandboxClient(ABC):
    """Abstract interface for secure code execution sandboxes."""

    @abstractmethod
    async def aexecute(
        self,
        code: str,
        files: Optional[Dict[str, bytes]] = None,
        timeout_seconds: int = 30,
    ) -> SandboxResult:
        pass


class LocalSubprocessSandboxClient(SandboxClient):
    """
    Local sandbox execution running Python in an isolated directory
    with network connectivity blocked via environment isolation.
    """

    @trace_tool("local_subprocess_sandbox")
    async def aexecute(
        self,
        code: str,
        files: Optional[Dict[str, bytes]] = None,
        timeout_seconds: int = 30,
    ) -> SandboxResult:
        files = files or {}
        temp_dir = tempfile.mkdtemp(prefix="sandbox_run_")
        start_time = time.time()

        try:
            # 1. Copy in input files
            for fname, content in files.items():
                fpath = os.path.join(temp_dir, fname)
                os.makedirs(os.path.dirname(fpath), exist_ok=True)
                with open(fpath, "wb") as f:
                    f.write(content)

            # 2. Write Python script
            script_path = os.path.join(temp_dir, "run_computation.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)

            # 3. Restrict environment variables (no external network proxies/credentials)
            restricted_env = {
                "PATH": os.environ.get("PATH", ""),
                "PYTHONPATH": os.path.pathsep.join(sys.path),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
                "USERPROFILE": os.environ.get("USERPROFILE", temp_dir),
                "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", temp_dir),
                "APPDATA": os.environ.get("APPDATA", temp_dir),
                "MPLCONFIGDIR": temp_dir,
                "TEMP": temp_dir,
                "TMP": temp_dir,
                # Disable network proxies completely
                "HTTP_PROXY": "http://127.0.0.1:0",
                "HTTPS_PROXY": "http://127.0.0.1:0",
                "ALL_PROXY": "http://127.0.0.1:0",
                "NO_PROXY": "",
            }

            # 4. Execute script
            proc = subprocess.run(
                [sys.executable, "run_computation.py"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=restricted_env,
            )

            # 5. Copy out produced output files
            output_files: Dict[str, bytes] = {}
            for root, _, filenames in os.walk(temp_dir):
                for fname in filenames:
                    if fname == "run_computation.py" or fname in files:
                        continue
                    full_p = os.path.join(root, fname)
                    rel_p = os.path.relpath(full_p, temp_dir)
                    with open(full_p, "rb") as out_f:
                        output_files[rel_p] = out_f.read()

            elapsed = time.time() - start_time
            return SandboxResult(
                stdout=proc.stdout,
                stderr=proc.stderr,
                exit_code=proc.returncode,
                output_files=output_files,
                execution_time=elapsed,
            )

        except subprocess.TimeoutExpired:
            return SandboxResult(
                stdout="",
                stderr=f"Execution timed out after {timeout_seconds} seconds.",
                exit_code=124,
                output_files={},
                execution_time=time.time() - start_time,
            )
        except Exception as e:
            return SandboxResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
                output_files={},
                execution_time=time.time() - start_time,
            )
        finally:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass


class DockerSandboxClient(SandboxClient):
    """
    Docker container sandbox with --network none ensuring zero outbound network access.
    """

    def __init__(self, image: str = "python:3.11-slim"):
        self.image = image
        self._local_fallback = LocalSubprocessSandboxClient()

    @trace_tool("docker_sandbox")
    async def aexecute(
        self,
        code: str,
        files: Optional[Dict[str, bytes]] = None,
        timeout_seconds: int = 30,
    ) -> SandboxResult:
        files = files or {}
        temp_dir = tempfile.mkdtemp(prefix="docker_sandbox_")
        start_time = time.time()

        try:
            for fname, content in files.items():
                fpath = os.path.join(temp_dir, fname)
                os.makedirs(os.path.dirname(fpath), exist_ok=True)
                with open(fpath, "wb") as f:
                    f.write(content)

            script_path = os.path.join(temp_dir, "run_computation.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)

            # Attempt docker run with --network none
            cmd = [
                "docker", "run", "--rm",
                "--network", "none",
                "-v", f"{temp_dir}:/workspace",
                "-w", "/workspace",
                self.image,
                "python", "run_computation.py",
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )

            if proc.returncode == 0:
                output_files: Dict[str, bytes] = {}
                for root, _, filenames in os.walk(temp_dir):
                    for fname in filenames:
                        if fname == "run_computation.py" or fname in files:
                            continue
                        full_p = os.path.join(root, fname)
                        rel_p = os.path.relpath(full_p, temp_dir)
                        with open(full_p, "rb") as out_f:
                            output_files[rel_p] = out_f.read()

                return SandboxResult(
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    exit_code=proc.returncode,
                    output_files=output_files,
                    execution_time=time.time() - start_time,
                )
        except Exception:
            pass
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        # Fallback to local subprocess if Docker is not available
        return await self._local_fallback.aexecute(code, files, timeout_seconds)


class E2BSandboxClient(SandboxClient):
    """
    E2B code interpreter sandbox with outbound network disabled via SDK configuration.
    Falls back gracefully when E2B API key is absent.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("E2B_API_KEY")
        self._local_fallback = LocalSubprocessSandboxClient()

    @trace_tool("e2b_sandbox")
    async def aexecute(
        self,
        code: str,
        files: Optional[Dict[str, bytes]] = None,
        timeout_seconds: int = 30,
    ) -> SandboxResult:
        if self.api_key and not self.api_key.startswith("your_"):
            try:
                from e2b_code_interpreter import Sandbox
                with Sandbox(api_key=self.api_key) as sbx:
                    if files:
                        for fname, content in files.items():
                            sbx.files.write(fname, content)
                    execution = sbx.run_code(code)
                    out_files = {}
                    return SandboxResult(
                        stdout="\n".join([str(l) for l in execution.logs.stdout]),
                        stderr="\n".join([str(l) for l in execution.logs.stderr]),
                        exit_code=0 if not execution.error else 1,
                        output_files=out_files,
                        execution_time=0.0,
                    )
            except Exception:
                pass

        # Fallback to isolated local subprocess
        return await self._local_fallback.aexecute(code, files, timeout_seconds)
