# ActionCenterAnnotationScannerAgent

An end-to-end AI-powered Java annotation framework that automatically discovers model/event/DTO classes in any Java repository, infers their event metadata using Claude AI, injects `@ActionCenterModel` annotations into the source, and generates a compile-time event catalog JSON.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│              actioncenter-agent  (AI Orchestrator)           │
│                                                              │
│  RepoScanner → ClassAnalyzer (Claude) → AnnotationInjector  │
│             → PomUpdater → BuildTrigger                      │
└──────────────────────────────────────────────────────────────┘
                          ↓ patches pom.xml + source files
┌──────────────────────────────────────────────────────────────┐
│           actioncenter-annotations  (JAR 1)                  │
│                                                              │
│   @ActionCenterModel    @ActionCenterField                   │
│   RetentionPolicy.SOURCE — zero runtime footprint            │
└──────────────────────────────────────────────────────────────┘
                          ↓ compile time (APT)
┌──────────────────────────────────────────────────────────────┐
│           actioncenter-scanner  (JAR 2)                      │
│                                                              │
│   ActionCenterAnnotationScanner extends AbstractProcessor    │
│   Runs during javac → writes action-center-catalog.json      │
└──────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
annotation-agent/
│
├── actioncenter-annotations/                    ← JAR 1: Annotation definitions
│   └── src/main/java/com/actioncenter/annotations/
│       ├── ActionCenterModel.java               ← @ActionCenterModel
│       └── ActionCenterField.java               ← @ActionCenterField
│
├── actioncenter-scanner/                        ← JAR 2: APT Processor
│   └── src/main/java/com/actioncenter/scanner/
│       └── ActionCenterAnnotationScanner.java   ← Generates event-catalog.json
│   └── src/main/resources/META-INF/services/
│       └── javax.annotation.processing.Processor
│
├── actioncenter-agent/                          ← AI Agent (Python CLI)
│   ├── scanner/repo_scanner.py                  ← Finds candidate classes
│   ├── analyzer/action_center_class_analyzer.py ← Claude API inference
│   ├── injector/action_center_annotation_injector.py ← Modifies .java files
│   ├── pom_updater/action_center_pom_updater.py ← Patches pom.xml
│   ├── build/action_center_build_trigger.py     ← Runs mvn compile
│   ├── ActionCenterAnnotationScannerAgent.py    ← Main orchestrator (entry point)
│   └── requirements.txt
│
└── pom.xml                                      ← Parent multi-module POM
```

---

## When Does Everything Run?

There are **two separate things running at two different times**. Understanding this distinction is important for partner teams.

```
DESIGN TIME (developer's machine or CI pipeline)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ① Partner team runs the AI Agent         ← ONE-TIME setup
        ↓
     Scans repo, injects @ActionCenterModel into source,
     patches pom.xml with JAR dependencies
        ↓
     Developer reviews the diff and commits to Git

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ② Every mvn compile / gradle build       ← EVERY BUILD
        ↓
     ActionCenterAnnotationScanner (APT) fires
     automatically inside javac — no manual step
        ↓
     Generates action-center-catalog.json inside the JAR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RUNTIME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Nothing runs. Zero overhead.
  Annotations are SOURCE-retained — stripped by the
  compiler. The catalog is a static JSON file in the JAR.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Responsibility Breakdown

| What | When | Who Triggers It | How Often |
|---|---|---|---|
| AI Agent | Design time | Developer runs it manually | Once at onboarding, then whenever new model classes are added |
| APT Scanner | Every compile | `mvn compile` or CI pipeline | Every single build, automatically |
| Runtime | Never | Nobody | Never — zero runtime footprint |

### Practical Day-to-Day for a Partner Team

```
Day 1 — Onboarding
  Developer runs the agent once against their repo
  12 classes get annotated, pom.xml gets patched
  Developer reviews the diff and commits to Git
  ✓ Onboarding complete — agent not needed again

Day 2 onwards — Normal dev cycle
  Team codes and builds as usual (mvn compile)
  APT Scanner fires silently inside every build
  Catalog JSON is regenerated automatically
  Team never thinks about the agent again

3 months later — 5 new event classes added
  Developer runs the agent once more
  Only unannotated classes are picked up and processed
  5 new classes get annotated, committed to Git
  ✓ Done
```

> **Key point:** The AI Agent is a one-time onboarding tool and occasional re-run helper — not something running continuously. The APT Scanner is what runs silently on every build, forever.

---

## Step 1: Build & Publish the JARs

```bash
# From repo root
mvn clean install

# This builds and installs both JARs to your local ~/.m2:
#   com.actioncenter:actioncenter-annotations:1.0.0
#   com.actioncenter:actioncenter-scanner:1.0.0
```

To publish to an internal Nexus/Artifactory, configure `distributionManagement` in the parent pom.xml and run `mvn deploy`.

---

## Step 2: Run the AI Agent on a Target Repo

### Prerequisites

```bash
cd actioncenter-agent
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_api_key_here
```

### Run

```bash
# Basic scan
python ActionCenterAnnotationScannerAgent.py scan --repo /path/to/team-repo

# Dry run (no file changes)
python ActionCenterAnnotationScannerAgent.py scan --repo /path/to/team-repo --dry-run

# Force overwrite existing annotations
python ActionCenterAnnotationScannerAgent.py scan --repo /path/to/team-repo --force

# Specify JAR version
python ActionCenterAnnotationScannerAgent.py scan --repo . --version 1.2.0

# Skip build step (inject only)
python ActionCenterAnnotationScannerAgent.py scan --repo . --skip-build
```

### What the Agent Does

```
① RepoScanner      → Finds *Event, *Model, *DTO, *Entity classes
② ClassAnalyzer    → Claude infers name, domain, description, fields
③ AnnotationInjector → Adds @ActionCenterModel + @ActionCenterField to source
④ PomUpdater       → Adds actioncenter JARs as provided dependencies
⑤ BuildTrigger     → Runs mvn compile (APT fires, JSON generated)
⑥ Summary report   → Shows what was changed and where the catalog is
```

### Example Output

```
════════════════════════════════════════════════════════════
  ActionCenterAnnotationScannerAgent
════════════════════════════════════════════════════════════
→ Repository : /home/dev/my-java-app
→ Dry run    : False

STEP 1 — Scanning for candidate classes
✓ Found 14 candidates  (12 new, 2 already annotated)

STEP 2 — Analyzing classes with Claude AI
  Analyzing: UserRegisteredEvent [high]
    → UserRegistered [auth] confidence=high
  Analyzing: OrderShippedEvent [high]
    → OrderShipped [fulfillment] confidence=high

STEP 3 — Injecting annotations
✓ Injected: UserRegisteredEvent
      Added imports: import com.actioncenter.annotations.ActionCenterModel;
      @ActionCenterField → userId
      @ActionCenterField → email
      @ActionCenterModel(name="UserRegistered", domain="auth") → class

STEP 4 — Updating pom.xml
✓ pom.xml updated
    Added actioncenter-annotations:1.0.0 (provided)
    Added actioncenter-scanner:1.0.0 (provided)

STEP 5 — Triggering build
✓ Build succeeded using maven
✓ Catalog generated → target/classes/actioncenter/action-center-catalog.json

  Catalog preview:
  Total events : 12
  Generated at : 2025-09-01T14:32:00Z
  • UserRegistered [auth] v1.0
  • OrderShipped [fulfillment] v1.0
  • PaymentProcessed [payments] v1.0
  ... and 9 more

════════════════════════════════════════════════════════════
  Summary
════════════════════════════════════════════════════════════
  Candidates scanned  : 14
  Event models found  : 12
  Annotations injected: 12
  Skipped             : 2
  Failed              : 0
```

---

## For Teams: Manual Usage (Without the Agent)

If you prefer to annotate classes manually without running the agent:

### 1. Add dependencies to your pom.xml

```xml
<dependency>
    <groupId>com.actioncenter</groupId>
    <artifactId>actioncenter-annotations</artifactId>
    <version>1.0.0</version>
    <scope>provided</scope>
</dependency>
<dependency>
    <groupId>com.actioncenter</groupId>
    <artifactId>actioncenter-scanner</artifactId>
    <version>1.0.0</version>
    <scope>provided</scope>
</dependency>
```

### 2. Annotate your model classes

```java
import com.actioncenter.annotations.ActionCenterModel;
import com.actioncenter.annotations.ActionCenterField;

@ActionCenterModel(
    name        = "UserRegistered",
    domain      = "auth",
    version     = "1.0",
    description = "Fired when a new user completes registration",
    tags        = {"user", "onboarding"}
)
public class UserRegisteredEvent {

    @ActionCenterField(description = "Unique user identifier", required = true)
    private String userId;

    @ActionCenterField(description = "User email address", sensitive = true, required = true)
    private String email;

    @ActionCenterField(description = "Timestamp of registration")
    private LocalDateTime registeredAt;
}
```

### 3. Build

```bash
mvn compile
# → generates: target/classes/actioncenter/action-center-catalog.json
```

---

## Generated Catalog: action-center-catalog.json

```json
{
  "generatedBy": "ActionCenterAnnotationScannerAgent",
  "generatedAt": "2025-09-01T14:32:00Z",
  "totalEvents": 1,
  "events": [
    {
      "className": "com.myapp.events.UserRegisteredEvent",
      "simpleName": "UserRegisteredEvent",
      "name": "UserRegistered",
      "domain": "auth",
      "version": "1.0",
      "description": "Fired when a new user completes registration",
      "tags": ["user", "onboarding"],
      "fields": [
        {
          "name": "userId",
          "type": "String",
          "fullType": "java.lang.String",
          "description": "Unique user identifier",
          "required": true,
          "sensitive": false,
          "example": "",
          "annotated": true
        },
        {
          "name": "email",
          "type": "String",
          "fullType": "java.lang.String",
          "description": "User email address",
          "required": true,
          "sensitive": true,
          "example": "",
          "annotated": true
        }
      ]
    }
  ]
}
```

---

## How It Works at Compile Time

1. Team runs `mvn compile`
2. `javac` discovers `ActionCenterAnnotationScanner` via `META-INF/services/javax.annotation.processing.Processor`
3. Scanner collects all `@ActionCenterModel` annotated classes
4. On the final processing round, it serializes them to JSON
5. JSON is written to `target/classes/actioncenter/action-center-catalog.json`
6. The JSON is packaged inside the team's JAR automatically

---

## Technology Stack

| Layer | Technology |
|---|---|
| Annotation definitions | Java 11, `RetentionPolicy.SOURCE` |
| APT Processor | `javax.annotation.processing.AbstractProcessor` |
| JSON generation | Jackson (shaded into processor JAR) |
| AI inference | Claude API (`claude-sonnet-4`) |
| Agent runtime | Python 3.9+ |
| Build detection | Maven / Gradle wrapper / Gradle |
| Source modification | Regex-based AST injection |