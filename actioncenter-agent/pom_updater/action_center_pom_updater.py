"""
ActionCenterPomUpdater
-----------------------
Adds the actioncenter-annotations and actioncenter-scanner JAR dependencies
to a team's existing pom.xml file.

Uses xml.etree.ElementTree to safely modify the XML rather than string hacking.
Skips if the dependencies are already present.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


ACTIONCENTER_GROUP_ID   = "com.actioncenter"
ANNOTATIONS_ARTIFACT_ID = "actioncenter-annotations"
SCANNER_ARTIFACT_ID     = "actioncenter-scanner"
DEFAULT_VERSION         = "1.0.0"

# Snippet for when XML manipulation fails or pom.xml not found
DEPENDENCY_SNIPPET = """
    <!-- ActionCenter Annotation Scanner Agent — add to your <dependencies> block -->
    <dependency>
        <groupId>com.actioncenter</groupId>
        <artifactId>actioncenter-annotations</artifactId>
        <version>{version}</version>
        <scope>provided</scope>
    </dependency>
    <dependency>
        <groupId>com.actioncenter</groupId>
        <artifactId>actioncenter-scanner</artifactId>
        <version>{version}</version>
        <scope>provided</scope>
    </dependency>
"""


@dataclass
class PomUpdateResult:
    pom_path: str
    success: bool
    already_present: bool = False
    changes: list = None
    snippet: Optional[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.changes is None:
            self.changes = []


class ActionCenterPomUpdater:
    """
    Safely patches a Maven pom.xml to include the ActionCenter JAR dependencies.

    Usage:
        updater = ActionCenterPomUpdater("/path/to/repo")
        result = updater.update(version="1.0.0")
        if result.success:
            print("pom.xml updated:", result.changes)
        elif result.snippet:
            print("Add manually:\\n", result.snippet)
    """

    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root).resolve()
        self.pom_path  = self.repo_root / "pom.xml"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, version: str = DEFAULT_VERSION) -> PomUpdateResult:
        if not self.pom_path.exists():
            return PomUpdateResult(
                pom_path=str(self.pom_path),
                success=False,
                error="pom.xml not found",
                snippet=DEPENDENCY_SNIPPET.format(version=version)
            )

        try:
            pom_text = self.pom_path.read_text(encoding="utf-8")
        except Exception as e:
            return PomUpdateResult(
                pom_path=str(self.pom_path),
                success=False,
                error=str(e),
                snippet=DEPENDENCY_SNIPPET.format(version=version)
            )

        # Check if already present
        if ANNOTATIONS_ARTIFACT_ID in pom_text and SCANNER_ARTIFACT_ID in pom_text:
            return PomUpdateResult(
                pom_path=str(self.pom_path),
                success=True,
                already_present=True
            )

        # Inject using string-safe insertion (preserves formatting/comments)
        try:
            updated, changes = self._inject_dependencies(pom_text, version)
            self.pom_path.write_text(updated, encoding="utf-8")
            return PomUpdateResult(
                pom_path=str(self.pom_path),
                success=True,
                changes=changes
            )
        except Exception as e:
            return PomUpdateResult(
                pom_path=str(self.pom_path),
                success=False,
                error=str(e),
                snippet=DEPENDENCY_SNIPPET.format(version=version)
            )

    # ------------------------------------------------------------------
    # Internal: inject dependencies block
    # ------------------------------------------------------------------

    def _inject_dependencies(self, pom_text: str, version: str):
        changes = []
        deps_to_add = []

        if ANNOTATIONS_ARTIFACT_ID not in pom_text:
            deps_to_add.append(self._dep_xml(ANNOTATIONS_ARTIFACT_ID, version))
            changes.append(f"Added {ANNOTATIONS_ARTIFACT_ID}:{version} (provided)")

        if SCANNER_ARTIFACT_ID not in pom_text:
            deps_to_add.append(self._dep_xml(SCANNER_ARTIFACT_ID, version))
            changes.append(f"Added {SCANNER_ARTIFACT_ID}:{version} (provided)")

        if not deps_to_add:
            return pom_text, changes

        block = "\n" + "\n".join(deps_to_add)

        # Try inserting inside existing <dependencies> block
        deps_close_match = re.search(r'(</dependencies>)', pom_text)
        if deps_close_match:
            insert_pos = deps_close_match.start()
            pom_text = pom_text[:insert_pos] + block + "\n    " + pom_text[insert_pos:]
            return pom_text, changes

        # No <dependencies> block — insert one before </project>
        project_close_match = re.search(r'(</project>)', pom_text)
        if project_close_match:
            insert_pos = project_close_match.start()
            deps_block = f"\n    <dependencies>{block}\n    </dependencies>\n"
            pom_text = pom_text[:insert_pos] + deps_block + pom_text[insert_pos:]
            changes.append("Created <dependencies> block")
            return pom_text, changes

        raise ValueError("Could not locate <dependencies> or </project> in pom.xml")

    @staticmethod
    def _dep_xml(artifact_id: str, version: str) -> str:
        return (
            f"        <dependency>\n"
            f"            <groupId>{ACTIONCENTER_GROUP_ID}</groupId>\n"
            f"            <artifactId>{artifact_id}</artifactId>\n"
            f"            <version>{version}</version>\n"
            f"            <scope>provided</scope>\n"
            f"        </dependency>"
        )
