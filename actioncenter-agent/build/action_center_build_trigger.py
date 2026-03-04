"""
ActionCenterBuildTrigger
-------------------------
Triggers the Maven/Gradle build in the target repository so that the
ActionCenterAnnotationScanner APT processor fires and generates the
event catalog JSON.

Supports: Maven (mvn), Gradle wrapper (./gradlew), Gradle global (gradle)
"""

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class BuildResult:
    success: bool
    tool_used: str
    command: str
    return_code: int
    stdout: str = ""
    stderr: str = ""
    catalog_path: Optional[str] = None
    error: Optional[str] = None


class ActionCenterBuildTrigger:
    """
    Triggers a compile in the target Java repository.

    Automatically detects whether to use Maven or Gradle based on
    what's present in the repository root.

    Usage:
        trigger = ActionCenterBuildTrigger("/path/to/repo")
        result = trigger.compile()
        if result.success:
            print("Catalog at:", result.catalog_path)
        else:
            print("Build failed:", result.stderr)
    """

    CATALOG_RELATIVE_PATH = "target/classes/actioncenter/action-center-catalog.json"

    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root).resolve()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compile(self) -> BuildResult:
        """Detect build tool and trigger compile."""
        tool, command = self._detect_build_tool()

        if not tool:
            return BuildResult(
                success=False,
                tool_used="none",
                command="",
                return_code=-1,
                error=(
                    "No build tool found. Expected one of: pom.xml (Maven), "
                    "gradlew (Gradle wrapper), or build.gradle (Gradle)."
                )
            )

        return self._run(tool, command)

    # ------------------------------------------------------------------
    # Build tool detection
    # ------------------------------------------------------------------

    def _detect_build_tool(self):
        if (self.repo_root / "pom.xml").exists():
            return "maven", ["mvn", "compile", "-q"]

        if (self.repo_root / "gradlew").exists():
            gradlew = "./gradlew"
            return "gradle-wrapper", [gradlew, "compileJava", "--quiet"]

        if (self.repo_root / "build.gradle").exists() or \
           (self.repo_root / "build.gradle.kts").exists():
            return "gradle", ["gradle", "compileJava", "--quiet"]

        return None, None

    # ------------------------------------------------------------------
    # Run the build
    # ------------------------------------------------------------------

    def _run(self, tool: str, command: List[str]) -> BuildResult:
        cmd_str = " ".join(command)
        try:
            result = subprocess.run(
                command,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            success = result.returncode == 0
            catalog_path = None

            if success:
                candidate = self.repo_root / self.CATALOG_RELATIVE_PATH
                if candidate.exists():
                    catalog_path = str(candidate)

            return BuildResult(
                success=success,
                tool_used=tool,
                command=cmd_str,
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                catalog_path=catalog_path
            )

        except subprocess.TimeoutExpired:
            return BuildResult(
                success=False,
                tool_used=tool,
                command=cmd_str,
                return_code=-1,
                error="Build timed out after 5 minutes"
            )
        except FileNotFoundError as e:
            return BuildResult(
                success=False,
                tool_used=tool,
                command=cmd_str,
                return_code=-1,
                error=f"Build tool not found on PATH: {e}. Is Maven/Gradle installed?"
            )
        except Exception as e:
            return BuildResult(
                success=False,
                tool_used=tool,
                command=cmd_str,
                return_code=-1,
                error=str(e)
            )
