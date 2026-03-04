"""
RepoScanner
-----------
Walks a Java repository's source tree and identifies candidate classes
that are likely event models, DTOs, or domain entities.

Candidate detection uses a combination of:
  - Class name suffix patterns (*Event, *Model, *DTO, *Entity, *Request, *Response)
  - Presence of common Java interfaces (Serializable)
  - Simple heuristics (field-heavy classes with no methods)
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class CandidateClass:
    """Represents a Java class identified as a candidate for @ActionCenterModel."""
    file_path: str
    package_name: str
    class_name: str
    source_code: str
    confidence: str = "medium"   # low | medium | high
    reason: str = ""
    already_annotated: bool = False


# Suffixes strongly suggestive of an event/model class
HIGH_CONFIDENCE_SUFFIXES = (
    "Event", "Model", "DTO", "Dto",
    "Request", "Response", "Payload", "Message"
)

MEDIUM_CONFIDENCE_SUFFIXES = (
    "Entity", "Record", "Data", "Info", "Detail"
)

ANNOTATION_MARKER = "@ActionCenterModel"


class RepoScanner:
    """
    Scans a Java repository for candidate @ActionCenterModel classes.

    Usage:
        scanner = RepoScanner("/path/to/repo")
        candidates = scanner.scan()
        for c in candidates:
            print(c.class_name, c.confidence, c.file_path)
    """

    def __init__(self, repo_root: str, src_subdir: str = "src/main/java"):
        self.repo_root = Path(repo_root).resolve()
        self.src_root  = self.repo_root / src_subdir

        if not self.src_root.exists():
            # Fallback: walk entire repo for .java files
            self.src_root = self.repo_root

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> List[CandidateClass]:
        """Return all candidate classes found under src/main/java."""
        candidates = []

        for java_file in self.src_root.rglob("*.java"):
            candidate = self._evaluate_file(java_file)
            if candidate:
                candidates.append(candidate)

        # Sort: high confidence first
        priority = {"high": 0, "medium": 1, "low": 2}
        candidates.sort(key=lambda c: priority.get(c.confidence, 3))

        return candidates

    # ------------------------------------------------------------------
    # Internal evaluation
    # ------------------------------------------------------------------

    def _evaluate_file(self, java_file: Path):
        try:
            source = java_file.read_text(encoding="utf-8")
        except Exception:
            return None

        # Skip interfaces, abstract classes, enums, annotations
        if re.search(r'\b(interface|enum|@interface)\b', source):
            return None
        if re.search(r'\babstract\s+class\b', source):
            return None

        class_name   = self._extract_class_name(source)
        package_name = self._extract_package(source)

        if not class_name:
            return None

        # Check if already annotated
        already_annotated = ANNOTATION_MARKER in source

        # Determine confidence
        confidence, reason = self._assess_confidence(class_name, source)

        if confidence == "skip":
            return None

        return CandidateClass(
            file_path=str(java_file),
            package_name=package_name,
            class_name=class_name,
            source_code=source,
            confidence=confidence,
            reason=reason,
            already_annotated=already_annotated,
        )

    def _assess_confidence(self, class_name: str, source: str):
        # Already annotated → still return it so the agent can skip/update
        if ANNOTATION_MARKER in source:
            return "high", "Already annotated with @ActionCenterModel"

        if any(class_name.endswith(s) for s in HIGH_CONFIDENCE_SUFFIXES):
            return "high", f"Class name matches high-confidence suffix"

        if any(class_name.endswith(s) for s in MEDIUM_CONFIDENCE_SUFFIXES):
            return "medium", f"Class name matches medium-confidence suffix"

        # Field-heavy class with no public methods → likely a POJO
        field_count  = len(re.findall(r'\bprivate\s+\w[\w<>,\s]+\s+\w+\s*;', source))
        method_count = len(re.findall(r'\bpublic\s+\w[\w<>]*\s+\w+\s*\(', source))

        if field_count >= 3 and method_count <= field_count:
            return "medium", f"Field-heavy POJO ({field_count} fields, {method_count} methods)"

        # Contains Serializable or common event base classes
        if "Serializable" in source or "BaseEvent" in source or "DomainEvent" in source:
            return "medium", "Implements Serializable or extends event base class"

        return "skip", ""

    @staticmethod
    def _extract_class_name(source: str) -> str:
        match = re.search(r'\bpublic\s+(?:final\s+)?class\s+(\w+)', source)
        return match.group(1) if match else ""

    @staticmethod
    def _extract_package(source: str) -> str:
        match = re.search(r'^\s*package\s+([\w.]+)\s*;', source, re.MULTILINE)
        return match.group(1) if match else ""
