"""
ActionCenterAnnotationInjector
-------------------------------
Injects @ActionCenterModel and @ActionCenterField annotations directly
into Java source files using regex-based AST manipulation.

Handles:
  - Adding the @ActionCenterModel annotation above the class declaration
  - Adding @ActionCenterField annotations above selected fields
  - Adding the required import statements
  - Skipping files that are already annotated (unless --force is passed)
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from analyzer.action_center_class_analyzer import AnalysisResult, FieldMetadata


ANNOTATIONS_IMPORT = "import com.actioncenter.annotations.ActionCenterModel;"
FIELD_IMPORT       = "import com.actioncenter.annotations.ActionCenterField;"


@dataclass
class InjectionResult:
    file_path: str
    success: bool
    skipped: bool = False
    skip_reason: str = ""
    error: Optional[str] = None
    changes_made: List[str] = None

    def __post_init__(self):
        if self.changes_made is None:
            self.changes_made = []


class ActionCenterAnnotationInjector:
    """
    Injects ActionCenter annotations into Java source files based on
    the metadata produced by ActionCenterClassAnalyzer.

    Usage:
        injector = ActionCenterAnnotationInjector()
        result = injector.inject(file_path="...", analysis=analysis_result)
        if result.success:
            print("Annotations injected:", result.changes_made)
    """

    def __init__(self, force: bool = False):
        """
        Args:
            force: If True, overwrite existing @ActionCenterModel annotations.
                   If False (default), skip already-annotated files.
        """
        self.force = force

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def inject(self, file_path: str, analysis: AnalysisResult) -> InjectionResult:
        """Inject annotations into the given Java source file."""
        path = Path(file_path)

        if not path.exists():
            return InjectionResult(file_path=file_path, success=False,
                                   error=f"File not found: {file_path}")

        try:
            source = path.read_text(encoding="utf-8")
        except Exception as e:
            return InjectionResult(file_path=file_path, success=False, error=str(e))

        # Guard: skip if already annotated and not forced
        if "@ActionCenterModel" in source and not self.force:
            return InjectionResult(
                file_path=file_path, success=True, skipped=True,
                skip_reason="@ActionCenterModel already present (use --force to overwrite)"
            )

        changes = []
        modified = source

        # Step 1: Inject imports
        modified, import_changes = self._inject_imports(modified, analysis)
        changes.extend(import_changes)

        # Step 2: Inject @ActionCenterField on fields
        modified, field_changes = self._inject_field_annotations(modified, analysis)
        changes.extend(field_changes)

        # Step 3: Inject @ActionCenterModel on class declaration
        modified, class_changes = self._inject_class_annotation(modified, analysis)
        changes.extend(class_changes)

        # Write back
        try:
            path.write_text(modified, encoding="utf-8")
        except Exception as e:
            return InjectionResult(file_path=file_path, success=False, error=str(e))

        return InjectionResult(
            file_path=file_path,
            success=True,
            changes_made=changes
        )

    # ------------------------------------------------------------------
    # Step 1: Inject import statements
    # ------------------------------------------------------------------

    def _inject_imports(self, source: str, analysis: AnalysisResult):
        changes = []
        imports_to_add = []

        if ANNOTATIONS_IMPORT not in source:
            imports_to_add.append(ANNOTATIONS_IMPORT)

        has_annotated_fields = any(f.include for f in analysis.fields)
        if has_annotated_fields and FIELD_IMPORT not in source:
            imports_to_add.append(FIELD_IMPORT)

        if not imports_to_add:
            return source, changes

        # Insert after the package declaration
        pkg_match = re.search(r'^(package\s+[\w.]+\s*;)', source, re.MULTILINE)
        if pkg_match:
            insert_pos = pkg_match.end()
            import_block = "\n" + "\n".join(imports_to_add)
            source = source[:insert_pos] + import_block + source[insert_pos:]
            changes.append(f"Added imports: {', '.join(imports_to_add)}")
        else:
            # No package statement — prepend at top
            source = "\n".join(imports_to_add) + "\n" + source
            changes.append(f"Added imports at top: {', '.join(imports_to_add)}")

        return source, changes

    # ------------------------------------------------------------------
    # Step 2: Inject @ActionCenterField on individual fields
    # ------------------------------------------------------------------

    def _inject_field_annotations(self, source: str, analysis: AnalysisResult):
        changes = []

        for field_meta in analysis.fields:
            if not field_meta.include:
                continue

            annotation = self._build_field_annotation(field_meta)

            # Match: private [type] [fieldName]; — with optional existing annotations
            # We look for the field declaration line and prepend the annotation
            pattern = rf'(\s*)((?:@\w+[^;{{}}]*\s*)*)(private\s+[\w<>, \[\]]+\s+{re.escape(field_meta.name)}\s*;)'
            match = re.search(pattern, source)

            if match:
                if "@ActionCenterField" not in match.group(0):
                    leading_ws = match.group(1)
                    replacement = f"{leading_ws}{annotation}\n{match.group(2)}{match.group(3)}"
                    source = source[:match.start()] + replacement + source[match.end():]
                    changes.append(f"  @ActionCenterField → {field_meta.name}")

        return source, changes

    # ------------------------------------------------------------------
    # Step 3: Inject @ActionCenterModel above class declaration
    # ------------------------------------------------------------------

    def _inject_class_annotation(self, source: str, analysis: AnalysisResult):
        changes = []
        annotation = self._build_class_annotation(analysis)

        # If force mode and already annotated, remove the old one first
        if self.force and "@ActionCenterModel" in source:
            source = re.sub(
                r'@ActionCenterModel\s*\([^)]*\)\s*\n',
                '',
                source
            )
            changes.append("Removed old @ActionCenterModel annotation")

        # Find the public class declaration
        class_match = re.search(
            r'(public\s+(?:final\s+)?class\s+\w+)',
            source
        )

        if class_match:
            insert_pos = class_match.start()
            source = source[:insert_pos] + annotation + "\n" + source[insert_pos:]
            changes.append(f"@ActionCenterModel(name=\"{analysis.name}\", domain=\"{analysis.domain}\") → class")
        else:
            changes.append("WARNING: Could not find class declaration to annotate")

        return source, changes

    # ------------------------------------------------------------------
    # Annotation string builders
    # ------------------------------------------------------------------

    def _build_class_annotation(self, analysis: AnalysisResult) -> str:
        tags_str = ", ".join(f'"{t}"' for t in analysis.tags)
        tags_attr = f',\n    tags        = {{{tags_str}}}' if analysis.tags else ''

        return (
            f'@ActionCenterModel(\n'
            f'    name        = "{analysis.name}",\n'
            f'    domain      = "{analysis.domain}",\n'
            f'    version     = "{analysis.version}",\n'
            f'    description = "{self._escape(analysis.description)}"{tags_attr}\n'
            f')'
        )

    def _build_field_annotation(self, field: FieldMetadata) -> str:
        parts = []
        if field.description:
            parts.append(f'description = "{self._escape(field.description)}"')
        if field.required:
            parts.append("required = true")
        if field.sensitive:
            parts.append("sensitive = true")
        if field.example:
            parts.append(f'example = "{self._escape(field.example)}"')

        attrs = ", ".join(parts)
        return f"    @ActionCenterField({attrs})"

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace('"', '\\"').replace('\n', ' ')
