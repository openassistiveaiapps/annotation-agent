#!/usr/bin/env python3
"""
ActionCenterAnnotationScannerAgent
====================================
Main orchestrator for the end-to-end annotation scanning and injection workflow.

Usage:
    python ActionCenterAnnotationScannerAgent.py scan --repo /path/to/repo
    python ActionCenterAnnotationScannerAgent.py scan --repo . --dry-run
    python ActionCenterAnnotationScannerAgent.py scan --repo . --force --version 1.2.0

Options:
    --repo       Path to the target Java repository (default: current directory)
    --version    Version of actioncenter JARs to add to pom.xml (default: 1.0.0)
    --dry-run    Analyze and report without modifying any files
    --force      Overwrite existing @ActionCenterModel annotations
    --skip-build Skip triggering mvn compile after injection
    --api-key    Anthropic API key (default: ANTHROPIC_API_KEY env var)
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure submodules are importable
sys.path.insert(0, str(Path(__file__).parent))

from scanner.repo_scanner import RepoScanner, CandidateClass
from analyzer.action_center_class_analyzer import ActionCenterClassAnalyzer, AnalysisResult
from injector.action_center_annotation_injector import ActionCenterAnnotationInjector
from pom_updater.action_center_pom_updater import ActionCenterPomUpdater
from build.action_center_build_trigger import ActionCenterBuildTrigger


# ─────────────────────────────────────────────────────────────────────────────
# Console formatting
# ─────────────────────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):    print(f"{GREEN}✓{RESET} {msg}")
def warn(msg):  print(f"{YELLOW}⚠{RESET} {msg}")
def fail(msg):  print(f"{RED}✗{RESET} {msg}")
def info(msg):  print(f"{CYAN}→{RESET} {msg}")
def header(msg): print(f"\n{BOLD}{msg}{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────────

class ActionCenterAnnotationScannerAgent:
    """
    Orchestrates the full ActionCenter annotation scanning workflow:

    1. Scan repo for candidate model/event/DTO classes
    2. Call Claude API to infer event metadata for each class
    3. Inject @ActionCenterModel and @ActionCenterField into source files
    4. Patch pom.xml with actioncenter-annotations + actioncenter-scanner deps
    5. Trigger mvn compile so the APT processor generates action-center-catalog.json
    6. Report summary
    """

    def __init__(self, repo: str, version: str, dry_run: bool,
                 force: bool, skip_build: bool, api_key: str = None):
        self.repo_root  = Path(repo).resolve()
        self.version    = version
        self.dry_run    = dry_run
        self.force      = force
        self.skip_build = skip_build

        self.scanner  = RepoScanner(str(self.repo_root))
        self.analyzer = ActionCenterClassAnalyzer(api_key=api_key)
        self.injector = ActionCenterAnnotationInjector(force=force)
        self.pom      = ActionCenterPomUpdater(str(self.repo_root))
        self.builder  = ActionCenterBuildTrigger(str(self.repo_root))

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self):
        print(f"\n{BOLD}{'═'*60}{RESET}")
        print(f"{BOLD}  ActionCenterAnnotationScannerAgent{RESET}")
        print(f"{BOLD}{'═'*60}{RESET}")
        info(f"Repository : {self.repo_root}")
        info(f"Dry run    : {self.dry_run}")
        info(f"Force      : {self.force}")

        # ── STEP 1: Scan ──────────────────────────────────────────────
        header("STEP 1 — Scanning for candidate classes")
        candidates = self.scanner.scan()

        if not candidates:
            warn("No candidate classes found. Nothing to do.")
            return

        total     = len(candidates)
        annotated = sum(1 for c in candidates if c.already_annotated)
        new_ones  = total - annotated

        ok(f"Found {total} candidates  "
           f"({new_ones} new, {annotated} already annotated)")

        # ── STEP 2: Analyze each class with Claude ────────────────────
        header("STEP 2 — Analyzing classes with Claude AI")
        analyses = []

        for candidate in candidates:
            if candidate.already_annotated and not self.force:
                info(f"  Skipping (already annotated): {candidate.class_name}")
                continue

            info(f"  Analyzing: {candidate.class_name} [{candidate.confidence}]")
            result = self.analyzer.analyze(
                class_name=candidate.class_name,
                source_code=candidate.source_code
            )

            if result.error:
                warn(f"    Claude error for {candidate.class_name}: {result.error}")
                continue

            if not result.is_event_model:
                info(f"    Skipped — not an event model: {candidate.class_name}")
                continue

            ok(f"    → {result.name} [{result.domain}] confidence={result.confidence}")
            analyses.append((candidate, result))

        if not analyses:
            warn("No classes identified as event models. Exiting.")
            return

        # ── STEP 3: Inject annotations ────────────────────────────────
        header("STEP 3 — Injecting annotations")
        injection_results = []

        for candidate, analysis in analyses:
            if self.dry_run:
                info(f"  [DRY RUN] Would inject @ActionCenterModel into: {candidate.class_name}")
                continue

            result = self.injector.inject(
                file_path=candidate.file_path,
                analysis=analysis
            )
            injection_results.append(result)

            if result.skipped:
                info(f"  Skipped: {candidate.class_name} — {result.skip_reason}")
            elif result.success:
                ok(f"  Injected: {candidate.class_name}")
                for change in result.changes_made:
                    print(f"      {change}")
            else:
                fail(f"  Failed: {candidate.class_name} — {result.error}")

        # ── STEP 4: Update pom.xml ────────────────────────────────────
        header("STEP 4 — Updating pom.xml")

        if self.dry_run:
            info(f"[DRY RUN] Would add actioncenter deps (v{self.version}) to pom.xml")
        else:
            pom_result = self.pom.update(version=self.version)
            if pom_result.already_present:
                info("pom.xml already contains actioncenter dependencies")
            elif pom_result.success:
                ok(f"pom.xml updated")
                for c in pom_result.changes:
                    print(f"    {c}")
            else:
                fail(f"pom.xml update failed: {pom_result.error}")
                if pom_result.snippet:
                    warn("Add these dependencies manually:")
                    print(pom_result.snippet)

        # ── STEP 5: Compile ───────────────────────────────────────────
        header("STEP 5 — Triggering build")

        if self.dry_run or self.skip_build:
            info("[DRY RUN / SKIP] Skipping mvn compile")
        else:
            build_result = self.builder.compile()
            if build_result.success:
                ok(f"Build succeeded using {build_result.tool_used}")
                if build_result.catalog_path:
                    ok(f"Catalog generated → {build_result.catalog_path}")
                    self._print_catalog_preview(build_result.catalog_path)
                else:
                    warn("Build succeeded but catalog file not found. "
                         "Check that @ActionCenterModel classes compiled correctly.")
            else:
                fail(f"Build failed (exit {build_result.return_code})")
                if build_result.stderr:
                    print(build_result.stderr[-2000:])  # Last 2000 chars of stderr

        # ── STEP 6: Summary ───────────────────────────────────────────
        self._print_summary(candidates, analyses, injection_results)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _print_catalog_preview(self, catalog_path: str):
        try:
            with open(catalog_path) as f:
                catalog = json.load(f)
            print(f"\n  {BOLD}Catalog preview:{RESET}")
            print(f"  Total events : {catalog.get('totalEvents', '?')}")
            print(f"  Generated at : {catalog.get('generatedAt', '?')}")
            for event in catalog.get("events", [])[:3]:
                print(f"  • {event['name']} [{event['domain']}] v{event['version']}")
            if catalog.get("totalEvents", 0) > 3:
                print(f"  ... and {catalog['totalEvents'] - 3} more")
        except Exception:
            pass

    def _print_summary(self, candidates, analyses, injection_results):
        print(f"\n{BOLD}{'═'*60}{RESET}")
        print(f"{BOLD}  Summary{RESET}")
        print(f"{BOLD}{'═'*60}{RESET}")
        print(f"  Candidates scanned  : {len(candidates)}")
        print(f"  Event models found  : {len(analyses)}")
        injected = sum(1 for r in injection_results if r.success and not r.skipped)
        skipped  = sum(1 for r in injection_results if r.skipped)
        failed   = sum(1 for r in injection_results if not r.success)
        print(f"  Annotations injected: {injected}")
        print(f"  Skipped             : {skipped}")
        print(f"  Failed              : {failed}")
        if self.dry_run:
            print(f"\n  {YELLOW}Dry run complete — no files were modified.{RESET}")
        print()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="actioncenter-agent",
        description="ActionCenterAnnotationScannerAgent — AI-powered Java annotation injector"
    )
    sub = parser.add_subparsers(dest="command")

    scan_cmd = sub.add_parser("scan", help="Scan a repo and inject ActionCenter annotations")
    scan_cmd.add_argument("--repo",       default=".", help="Path to Java repository root")
    scan_cmd.add_argument("--version",    default="1.0.0", help="JAR version for pom.xml")
    scan_cmd.add_argument("--dry-run",    action="store_true", help="Report without modifying files")
    scan_cmd.add_argument("--force",      action="store_true", help="Overwrite existing annotations")
    scan_cmd.add_argument("--skip-build", action="store_true", help="Skip mvn compile step")
    scan_cmd.add_argument("--api-key",    default=None, help="Anthropic API key")

    args = parser.parse_args()

    if args.command == "scan":
        agent = ActionCenterAnnotationScannerAgent(
            repo=args.repo,
            version=args.version,
            dry_run=args.dry_run,
            force=args.force,
            skip_build=args.skip_build,
            api_key=args.api_key or os.environ.get("ANTHROPIC_API_KEY")
        )
        agent.run()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
