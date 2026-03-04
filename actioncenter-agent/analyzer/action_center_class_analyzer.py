"""
ActionCenterClassAnalyzer
--------------------------
Sends Java class source code to the Claude API and receives structured
event metadata back. This is the AI brain of the ActionCenterAnnotationScannerAgent.

Claude infers:
  - event name        (e.g. "UserRegistered")
  - domain            (e.g. "auth")
  - description       (natural language)
  - relevant fields   (which fields matter for the event catalog)
  - field metadata    (required, sensitive, description per field)
  - confidence        (how sure Claude is about this class being an event model)
"""

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional

import anthropic

CLAUDE_MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are an expert Java architect helping to classify domain event classes
for the ActionCenter system.

Given a Java class, you must determine:
1. Whether it represents a domain event, DTO, or model that should be registered in an event catalog.
2. What metadata to attach to it via @ActionCenterModel and @ActionCenterField annotations.

Always respond with ONLY a valid JSON object — no explanation, no markdown, no preamble.

JSON shape:
{
  "is_event_model": true,
  "confidence": "high|medium|low",
  "name": "PascalCase event name (verb + noun, e.g. UserRegistered)",
  "domain": "lowercase bounded context (e.g. auth, payments, notifications)",
  "version": "1.0",
  "description": "One sentence: when and why this event is raised",
  "tags": ["tag1", "tag2"],
  "fields": [
    {
      "name": "fieldName",
      "include": true,
      "description": "what this field represents",
      "required": true,
      "sensitive": false,
      "example": "optional example value"
    }
  ],
  "reasoning": "brief note on why you made these decisions"
}

If the class is NOT an event model (e.g. it is a service, repository, or utility), set:
  "is_event_model": false
and omit the other fields.
"""


@dataclass
class FieldMetadata:
    name: str
    include: bool
    description: str = ""
    required: bool = False
    sensitive: bool = False
    example: str = ""


@dataclass
class AnalysisResult:
    class_name: str
    is_event_model: bool
    confidence: str = "low"
    name: str = ""
    domain: str = ""
    version: str = "1.0"
    description: str = ""
    tags: List[str] = field(default_factory=list)
    fields: List[FieldMetadata] = field(default_factory=list)
    reasoning: str = ""
    raw_response: str = ""
    error: Optional[str] = None


class ActionCenterClassAnalyzer:
    """
    Calls the Claude API to analyze a Java class and infer ActionCenter
    event metadata from its source code.

    Usage:
        analyzer = ActionCenterClassAnalyzer()
        result = analyzer.analyze(class_name="UserRegisteredEvent", source_code="...")
        if result.is_event_model:
            print(result.name, result.domain, result.description)
    """

    def __init__(self, api_key: Optional[str] = None):
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, class_name: str, source_code: str) -> AnalysisResult:
        """Send class source to Claude and parse the structured response."""
        user_message = self._build_prompt(class_name, source_code)

        try:
            response = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}]
            )

            raw = response.content[0].text.strip()
            return self._parse_response(class_name, raw)

        except Exception as e:
            return AnalysisResult(
                class_name=class_name,
                is_event_model=False,
                error=str(e)
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, class_name: str, source_code: str) -> str:
        return (
            f"Analyze this Java class and return the structured JSON metadata.\n\n"
            f"Class name: {class_name}\n\n"
            f"Source code:\n```java\n{source_code}\n```"
        )

    def _parse_response(self, class_name: str, raw: str) -> AnalysisResult:
        # Strip any accidental markdown fences
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return AnalysisResult(
                class_name=class_name,
                is_event_model=False,
                error=f"JSON parse error: {e}  |  Raw: {raw[:200]}"
            )

        if not data.get("is_event_model", False):
            return AnalysisResult(
                class_name=class_name,
                is_event_model=False,
                reasoning=data.get("reasoning", ""),
                raw_response=raw
            )

        fields = [
            FieldMetadata(
                name=f.get("name", ""),
                include=f.get("include", True),
                description=f.get("description", ""),
                required=f.get("required", False),
                sensitive=f.get("sensitive", False),
                example=f.get("example", ""),
            )
            for f in data.get("fields", [])
        ]

        return AnalysisResult(
            class_name=class_name,
            is_event_model=True,
            confidence=data.get("confidence", "medium"),
            name=data.get("name", class_name),
            domain=data.get("domain", ""),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            fields=fields,
            reasoning=data.get("reasoning", ""),
            raw_response=raw
        )
