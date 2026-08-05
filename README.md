# Aegis SDK — Advanced Security Technical Reference
## For Cybersecurity Expert Analysis

> This document is a complete technical reference for the Aegis Agent SDK. It is written to enable a thorough security audit of the system, including all layers, implemented mechanisms, known gaps, architectural trade-offs, and remaining open attack surfaces.

---

## Table of Contents

1. [Overview & Threat Model](#1-overview--threat-model)
2. [Architecture Summary](#2-architecture-summary)
3. [Project Structure](#3-project-structure)
4. [Layer 1 — Request Intelligence & Pre-Execution Firewall](#4-layer-1--request-intelligence--pre-execution-firewall)
5. [Layer 2 — Execution Governance](#5-layer-2--execution-governance)
6. [Layer 3 — Secure Runtime Control Plane](#6-layer-3--secure-runtime-control-plane)
7. [Layer 4 — Memory & State Security](#7-layer-4--memory--state-security)
8. [Layer 5 — Output Control & Indirect Injection Defense](#8-layer-5--output-control--indirect-injection-defense)
9. [Policy Engine — Natural Language Guardrails](#9-policy-engine--natural-language-guardrails)
10. [HITL — Human-in-the-Loop Enforcement](#10-hitl--human-in-the-loop-enforcement)
11. [Observability & Telemetry](#11-observability--telemetry)
12. [Cloud Backend Telemetry Store](#12-cloud-backend-telemetry-store)
13. [Governance Scoring](#13-governance-scoring)
14. [Event Bus & Kill Switch](#14-event-bus--kill-switch)
15. [Framework Adapters (LangGraph / CrewAI)](#15-framework-adapters-langgraph--crewai)
16. [Cloud Backend & Dashboard](#16-cloud-backend--dashboard)
17. [Data Flow — End-to-End Execution Trace](#17-data-flow--end-to-end-execution-trace)
18. [Known Limitations & Open Attack Surfaces](#18-known-limitations--open-attack-surfaces)
19. [Dependency Stack & Supply-Chain Surface](#19-dependency-stack--supply-chain-surface)
20. [Roadmap Security Items](#20-roadmap-security-items)
21. [Quick Start](#21-quick-start)

---

## 1. Overview & Threat Model

Aegis is a Python-based **security-first Agent SDK** that wraps LangGraph-based LLM agents with a multi-layer security architecture. It is designed to be the trust boundary between untrusted user input and potentially destructive AI-driven tool execution.

### 1.1 Design Principles

- **Composition over inheritance** — every security layer is a swappable, independently testable component behind a `Protocol` interface.
- **Fail-closed** — on errors in any security layer (LLM timeouts, rate limits, validation failures), execution is blocked rather than permitted.
- **Defense in depth** — five independent security layers with no single point of bypass.
- **Principle of least privilege** — Layer 1 restricts the exact tool set the agent may use per-request. Layer 2 verifies this at execution time.

### 1.2 Threat Categories

| # | Threat | Layer Defense |
|---|---|---|
| A | Direct Prompt Injection | Layer 1 LLM Firewall |
| B | Indirect Prompt Injection (tool outputs) | Layer 5 Sanitizer |
| C | Tool Privilege Escalation | Layer 1 (allowlist) + Layer 2 (enforcement) |
| D | Unauthorized Tool Invocation | Layer 2 ToolAuthorizationValidator |
| E | Malicious Tool Arguments | Layer 2 ToolArgumentValidator |
| F | Memory Poisoning | Layer 1 MemoryValidationStage |
| G | Jailbreak / Role Hijacking | Layer 1 RequestAnalyzerStage |
| H | Policy Violations | NaturalLanguagePolicy + evaluate_output |
| I | Unauthenticated Execution | Layer 2 IdentityValidator |
| J | Unauthorized Role Access | Layer 2 PermissionValidator |

### 1.3 Out of Scope

- Network-level denial of service
- Physical infrastructure attacks
- Vulnerabilities in underlying Python/OS runtime

---

## 2. Architecture Summary

```
User Request
    │
    ▼
┌─────────────────────────────────────────────┐
│  LAYER 1: Request Intelligence & Firewall    │
│  ┌───────────────────────────────────────┐  │
│  │  RequestAnalyzerStage                 │  │
│  │  • Safety / Injection check           │  │
│  │  • Intent analysis                    │  │
│  │  • Tool allowlist (least privilege)   │  │
│  │  • Risk scoring (LOW/MED/HIGH/CRIT)   │  │
│  └──────────────────┬────────────────────┘  │
│  ┌───────────────────▼────────────────────┐  │
│  │  MemoryValidationStage                 │  │
│  │  • Context window overflow check       │  │
│  │  • Heuristic poisoning pattern scan    │  │
│  │  • LLM semantic memory poison scan     │  │
│  └───────────────────┬────────────────────┘  │
└──────────────────────┼──────────────────────┘
                       │ passes Layer 1
    ▼
┌─────────────────────────────────────────────┐
│  HITL GATE (if HIGH/CRITICAL risk)           │
│  Requires "I approve" before proceeding      │
└──────────────────────┬──────────────────────┘
                       │
    ▼
┌─────────────────────────────────────────────┐
│  NATURAL LANGUAGE POLICY ENGINE              │
│  evaluate_input() → LLM governance check    │
└──────────────────────┬──────────────────────┘
                       │
    ▼
┌─────────────────────────────────────────────┐
│  LangGraph Planner (LLM)                     │
│  Generates tool call decisions               │
└──────────────────────┬──────────────────────┘
                       │
    ▼  (per tool call)
┌─────────────────────────────────────────────┐
│  LAYER 2: Execution Governance               │
│  ┌──────────────────────────────────────┐   │
│  │  IdentityValidator   (JWT/API key)   │   │
│  │  PermissionValidator (RBAC/scopes)   │   │
│  │  ToolAuthorizationValidator          │   │
│  │  ToolArgumentValidator               │   │
│  └──────────────────────────────────────┘   │
└──────────────────────┬──────────────────────┘
                       │ approved
    ▼
┌─────────────────────────────────────────────┐
│  LAYER 3: Runtime Control Plane              │
│  TimeoutManager → RetryManager → ToolExecutor│
└──────────────────────┬──────────────────────┘
                       │
    ▼
┌─────────────────────────────────────────────┐
│  LAYER 5: Output Sanitization                │
│  IndirectInjectionSanitizer                  │
│  → Boundary tagging, Unicode normalization,  │
│    Base64 inspection, token disarming        │
└──────────────────────┬──────────────────────┘
                       │
    ▼
┌─────────────────────────────────────────────┐
│  POLICY OUTPUT VALIDATION                    │
│  evaluate_output() → LLM response audit      │
└──────────────────────┬──────────────────────┘
                       │
    ▼
Final Response + ExecutionReport (telemetry)
```

---

## 3. Project Structure

```
aegis/
└── packages/
    ├── aegis.py                     # Public SDK facade (Aegis class)
    ├── context.py                   # ExecutionContext, Layer1Context
    ├── models.py                    # ProposedAction, AgentRequest, GovernanceResult
    ├── config.py                    # AegisConfig
    │
    ├── layers/
    │   ├── layer1/
    │   │   ├── base.py              # Layer1Stage protocol
    │   │   ├── exceptions.py        # PromptValidationError, MemoryValidationError, Layer1ProcessingError
    │   │   └── stages/
    │   │       ├── request_analyzer.py    # Unified LLM security analyzer [ACTIVE]
    │   │       └── memory_validation.py  # Context overflow + poisoning scanner [ACTIVE]
    │   └── layer2/
    │       ├── engine.py            # GovernanceEngine — runs all validators in sequence
    │       └── validators.py        # IdentityValidator, PermissionValidator,
    │                                #   ToolAuthorizationValidator, ToolArgumentValidator [ALL ACTIVE]
    │
    ├── policy/
    │   ├── base.py                  # PolicyProvider, PolicyViolationError, ApprovalRequiredError
    │   └── nl_policy.py             # NaturalLanguagePolicy (input + output validation) [ACTIVE]
    │
    ├── runtime/
    │   ├── factory.py               # RuntimeFactory — wires all components
    │   ├── graph.py                 # build_agent_graph (LangGraph)
    │   ├── kernel/
    │   │   ├── kernel.py            # RuntimeKernel — main orchestration loop
    │   │   └── state.py             # LangGraph State schema
    │   ├── nodes/
    │   │   ├── planner.py           # PlannerNode — LLM decision node
    │   │   └── executor.py          # ExecutorNode — Layer 2 + Layer 3 bridge
    │   ├── managers/
    │   │   ├── registry.py          # ToolRegistry — registered tool store
    │   │   ├── executor.py          # ToolExecutor — calls tool.invoke()
    │   │   ├── timeout.py           # TimeoutManager — asyncio.wait_for wrapper
    │   │   ├── retry.py             # RetryManager — none/fixed/linear/exponential
    │   │   ├── normalizer.py        # ResultNormalizer — truncation + sanitization
    │   │   ├── sanitizer.py         # IndirectInjectionSanitizer — Layer 5 [ACTIVE]
    │   │   ├── monitor.py           # BehaviorMonitor — event graph subscriber
    │   │   ├── supervisor.py        # ExecutionSupervisor
    │   │   ├── tracker.py           # ExecutionTracker
    │   │   └── kill_switch.py       # KillSwitchManager
    │   ├── events/
    │   │   ├── bus.py               # RuntimeEventBus
    │   │   └── models.py            # ToolStarted, ExecutionStarted, KillSwitchActivated, etc.
    │   └── hooks/
    │       ├── base.py              # HookManager, RuntimeHook protocol
    │       └── policy.py            # PolicyHook — calls evaluate_input/output/tool
    │
    ├── memory/
    │   ├── manager.py               # MemoryManager
    │   ├── registry.py              # MemoryRegistry
    │   ├── semantic.py              # SemanticMemory
    │   ├── retrieval.py             # KnowledgeRetrieval
    │   └── adapters/
    │       └── langgraph_adapter.py # LangGraph MemorySaver adapter
    │
    ├── observability/
    │   ├── models.py                # ExecutionReport, GovernanceReport, GovernanceScore, etc.
    │   └── store.py                 # JsonExecutionStore, AegisCloudExecutionStore
    │
    └── adapters/
        ├── base/adapter.py          # FrameworkAdapter protocol
        ├── langgraph/adapter.py     # LangGraphAdapter + AegisTelemetryHandler [ACTIVE]
        └── crewai/adapter.py        # CrewAIAdapter + CrewAITelemetryHandler [ACTIVE]
```

---

## 4. Layer 1 — Request Intelligence & Pre-Execution Firewall

**File**: `aegis/packages/layers/layer1/stages/`

Layer 1 is the **first and most critical security gate**. It runs before the LLM planner and before any tool is considered for invocation. It uses a dedicated, temperature=0 security LLM instance with structured output enforcement.

### 4.1 RequestAnalyzerStage

**File**: `aegis/packages/layers/layer1/stages/request_analyzer.py`

A single LLM call that simultaneously performs four security functions:

**1. Safety Validation**
- Detects prompt injection, jailbreaks, unauthorized access attempts, and malicious intent.
- Returns `is_safe: bool`. On `False`, raises `PromptValidationError` → execution is immediately aborted.
- Context-aware: receives the last 4 conversation turns to understand approval context.
- Non-semantic prompts (too short, no alphanumeric content) are blocked before any LLM call.

**2. Intent & Task Classification**
- Extracts `primary_intent`, `task_category`, `required_capabilities`, and `confidence_score`.
- Uses structured output (`RequestAnalysisResult` Pydantic model) — hallucinated JSON structure is rejected.

**3. Tool Allowlist (Principle of Least Privilege)**
- Layer 1 selects only the specific tools required for the request from the registered tool list.
- Output is **cross-validated** against registered tool names — hallucinated tool names are silently dropped:

```python
valid_tool_names = {get_tool_name(t) for t in self.available_tools}
filtered_tools = [t for t in result.allowed_tools if t in valid_tool_names]
context.layer1.allowed_tools = filtered_tools
```

**Security implication**: Even if the security LLM hallucinates a tool name, it will be silently dropped. Only registered tools can ever be invoked.

**4. Risk Assessment**
- Assigns `risk_level` (LOW/MEDIUM/HIGH/CRITICAL) and `risk_score` (0.0–1.0).
- Assigns `execution_recommendation`: `execute_normally`, `require_human_approval`, or `block`.
- HIGH and CRITICAL risk automatically triggers the HITL gate.

### 4.2 System Prompt

The Layer 1 system prompt instructs the security LLM:
- It is a **cybersecurity analyzer only** — not an executor.
- To apply context-awareness: "I approve" should not be blocked (it's a HITL phrase, handled by Layer 2).
- To apply least privilege: return only exactly necessary tools.
- To mark high-risk operations HIGH/CRITICAL rather than blocking them outright (HITL handles approval).

### 4.3 MemoryValidationStage

**File**: `aegis/packages/layers/layer1/stages/memory_validation.py`

Runs after the request analyzer. Defends against:
- **Context window overflow attacks** (enforces character limit on total history, default 10,000 chars)
- **Memory poisoning** (detects malicious instructions, system overrides, and state-hijacking payloads in conversation history)

> **Implementation State**: Fully active dual-phase memory validation. Combines context window size limits, pattern-based injection checks, and LLM-based semantic scanning for memory poisoning and instruction overrides in historical context.

**Three-phase validation:**

1. **Context Window Size Enforcement**: Inspects `recent_messages`, `history`, `messages` in context state. Rejects requests exceeding `max_context_size` (default 10,000 chars).

2. **Heuristic Pattern Scanner** — 12 active patterns:
   - `ignore (all) previous instructions`
   - `disregard (all) previous rules/guidelines`
   - `forget (all) previous context`
   - `override (system) prompt/rules`
   - `system: you are now`
   - `new system instructions:`
   - `bypass (safety/security) rules/filters`
   - `remember this new rule:`
   - `always (execute/run) [tool] without approval`
   - `hidden instruction:`
   - `admin override:`
   - `you are now in developer mode`

3. **LLM Semantic Memory Scan**: When `GROQ_API_KEY` is available, runs a dedicated `MemoryPoisoningResult`-structured LLM scan on conversation history to detect subtle, paraphrased, or cross-turn injection attempts.

### 4.4 Conversation History Context

Layer 1 receives the last 4 conversation turns to evaluate **approval context** correctly.

### 4.5 Layer 1 Exceptions

```python
PromptValidationError   # Unsafe prompt → execution immediately aborted
MemoryValidationError   # Memory poisoning or context overflow detected
Layer1ProcessingError   # Analyzer LLM failure (rate limit, network) → fail-closed
```

---

## 5. Layer 2 — Execution Governance

**File**: `aegis/packages/layers/layer2/`

Layer 2 is the **strict trust boundary** between the untrusted LLM planner and the tool execution engine. It runs once per proposed tool call, not once per request.

### 5.1 Architecture

```
LLM Planner output
     |
     v  (tool_calls in AIMessage)
ExecutorNode.__call__()
     |
     v
ProposedAction(tool_name, arguments, reasoning)
     |
     v
GovernanceEngine.evaluate(action, context)
     |
     +-- ToolScopeValidator       <- Enforces optional caller-level allowed_tools restriction
     +-- ToolAuthorizationValidator  <- Enforces Layer 1 allowlist at execution time
     +-- ToolArgumentValidator    <- Sanitizes tool input parameters
     |
     +-- DENIED  --> ToolMessage("Execution blocked by Layer 2...") + telemetry
     +-- APPROVED --> Layer 3 execution
```

### 5.2 ToolScopeValidator (Active)

Performs caller-level tool restrictions:
- Developers can pass an explicit `allowed_tools` list on `agent.run(prompt, allowed_tools=["db_query"])`.
- At execution time, `ToolScopeValidator` verifies that the proposed tool call exists within the caller's restricted tool set.
- Clean, non-intrusive scope enforcement without requiring complex authentication or RBAC frameworks inside the SDK.

### 5.3 Layer 2 Validators Summary

| Validator | Function | Implementation |
|---|---|---|
| `ToolScopeValidator` | Per-call Tool Restriction | Enforces optional developer-provided `allowed_tools` list passed to `agent.run()` |
| `ToolAuthorizationValidator` | Layer 1 Allowlist Enforcement | Enforces Layer 1 least-privilege tool allowlist at execution time |
| `ToolArgumentValidator` | Parameter Sanitization | Prevents SQL injection, path traversal, malformed JSON, and command injection in tool inputs |

### 5.5 ToolAuthorizationValidator (Active)

```python
class ToolAuthorizationValidator:
    async def validate(self, action, context):
        allowed_tools = context.layer1.allowed_tools
        if action.tool_name not in allowed_tools:
            raise PolicyViolationError(f"Unauthorized tool '{action.tool_name}'...")
```

This is the **double-lock mechanism**: Layer 1 restricts what tools are allowed for a request. Layer 2 verifies at the moment of execution that the LLM is only calling tools from that approved set.

**HITL bypass path**: If the user prompt is an approval phrase, the `ToolAuthorizationValidator` bypasses the allowlist check. This is intentional — approval phrases carry no tool context from Layer 1.

### 5.6 ToolArgumentValidator (Active)

Defends against **tool parameter injection attacks**:

| Check | Pattern | Attack Prevented |
|---|---|---|
| Database table name | `^[a-zA-Z0-9_]+$` only | SQL injection via table parameter |
| JSON argument validity | `json.loads()` on known keys | Malformed JSON payload attacks |
| Path traversal | `../`, `..\` | Directory traversal |
| Shell injection | `rm -rf`, `eval(`, `exec(` | Command injection |
| Script injection | `<script`, `javascript:` | XSS in stored results |

---

## 6. Layer 3 — Secure Runtime Control Plane

Layer 3 is the set of managers responsible for the **actual execution** of approved tool calls.

### 6.1 ToolRegistry

`aegis/packages/runtime/managers/registry.py`
- Maintains a map of `tool_name -> RegisteredTool(metadata, executable)`
- `ToolMetadata` includes: timeout, retry policy, permissions list, tags
- Prevents execution of tools not in the registry even if governance passes

### 6.2 TimeoutManager

`aegis/packages/runtime/managers/timeout.py`
```python
await asyncio.wait_for(coroutine_func(**kwargs), timeout=timeout_seconds)
```
- Every tool execution has a strict, per-tool configurable timeout (default 30s)
- On timeout, returns a structured `ExecutionMetadata(timeout_occurred=True)` — never hangs
- Prevents **resource exhaustion via slow tool calls** (Denial of Service against the agent)

### 6.3 RetryManager

`aegis/packages/runtime/managers/retry.py`

Supports four retry policies: `none`, `fixed`, `linear`, `exponential`. All exponential retries include **+/- 20% jitter** to prevent thundering herd:

```
delay = base_delay * (2 ** attempt)
jitter = delay * 0.2 * random.uniform(-1, 1)
final_delay = max(0, delay + jitter)
```

### 6.4 ToolExecutor

`aegis/packages/runtime/managers/executor.py`
- Calls `tool.invoke(args)` via the LangChain `BaseTool` interface
- Handles sync tools via `asyncio.get_event_loop().run_in_executor(None, ...)`

### 6.5 ResultNormalizer

`aegis/packages/runtime/managers/normalizer.py`
1. **Binary data** → replaced with `[BINARY DATA OMITTED: N bytes]`
2. **JSON/dicts** → serialized to compact JSON
3. **HTML strings** → flagged for future BeautifulSoup stripping
4. **Universal truncation** → capped at 4,000 characters
5. **Sanitization** → passed through `IndirectInjectionSanitizer` (Layer 5)

### 6.6 BehaviorMonitor

Subscribes to **all** runtime events via the event bus. Builds a complete chronological execution graph similar to LangSmith.

---

## 7. Layer 4 — Memory & State Security

**Files**: `aegis/packages/memory/`

The memory subsystem supports pluggable backends via the `MemoryProvider` protocol:

```python
class MemoryProvider(Protocol):
    async def store(self, key: str, value: Any) -> None: ...
    async def recall(self, key: str) -> Any | None: ...
    async def clear(self) -> None: ...
```

### 7.1 Session Isolation

LangGraph's `MemorySaver` is configured with `thread_id = context.correlation_id`. Each unique `correlation_id` produces an isolated memory namespace. This prevents **cross-session memory bleed**.

### 7.2 Memory Threat Vectors

| Threat | Defense | Status |
|---|---|---|
| Context overflow | `max_context_size = 10,000` chars in `MemoryValidationStage` | Active |
| Session bleed | Isolated by `correlation_id` thread key | Active |
| Memory poisoning | Heuristic pattern scanning + LLM semantic scan in `MemoryValidationStage` | Active |
| Replay attacks | No replay protection | Not implemented |

---

## 8. Layer 5 — Output Control & Indirect Injection Defense

**File**: `aegis/packages/runtime/managers/sanitizer.py`

`IndirectInjectionSanitizer` defends against malicious instructions embedded inside data that the LLM reads (YouTube transcripts, email bodies, GitHub issues, database results).

### 8.1 Active Defense Pipeline

The `IndirectInjectionSanitizer` uses a **multi-stage normalization and disarming pipeline**:

1. **Unicode Homograph & Zero-Width Character Normalization**:
   - Applies NFKC Unicode normalization (`unicodedata.normalize("NFKC")`) to collapse homograph substitutions (e.g. `ⅈgnore` → `ignore`).
   - Strips hidden zero-width spaces (`\u200b`, `\u200c`, `\u200d`, `\ufeff`) and ASCII control characters used to obscure injection words.

2. **Structural Delimiter Breakout Prevention**:
   - Detects and escapes raw closing/opening boundary tags inside tool output (e.g. `</untrusted_tool_output>`) to prevent attackers from breaking out of data demarcations.

3. **Base64 Payload Inspection & Neutralization**:
   - Automatically detects Base64-encoded strings, decodes them, and scans the decoded payload for injection directives. If found, neutralizes the payload as `[NEUTRALIZED_BASE64_INDIRECT_INJECTION_PAYLOAD]`.

4. **Special LLM Control Token Disarming**:
   - Neutralizes ChatML and prompt format control tokens (`<|im_start|>`, `<|im_end|>`, `[INST]`, `[/INST]`, `[SYSTEM]`, `<<SYS>>`, `<|endoftext|>`).

5. **Expanded High-Precision Pattern Matrix** (18 patterns across 4 categories):
   - Directive overrides: `ignore previous instructions`, `override system prompt`, `new system instructions:`
   - Exfiltration: `forward all emails/passwords to`, `send all data to`, `exfiltrate to`
   - Role hijacking: `you are now DAN/godmode/jailbroken`, `act as root`, `developer mode enabled`
   - Security bypass: `bypass safety filters`, `disable security checks`

### 8.2 Neutralization & Structural Enclosure

Detected injection patterns and tokens are disarmed as `[NEUTRALIZED_INDIRECT_PROMPT_INJECTION_DIRECTIVE]`, and content is safely enclosed in structural boundary tags:

```xml
<untrusted_tool_output tool='email_reader'>
  ... sanitized content ...
</untrusted_tool_output>
```

This instructs the LLM explicitly that the text is untrusted external data, not system commands.

---

## 9. Policy Engine — Natural Language Guardrails

**File**: `aegis/packages/policy/nl_policy.py`

The `NaturalLanguagePolicy` allows developers to express governance rules in plain English:

```python
agent.with_policy("Never allow access to production databases without explicit approval")
agent.with_policy("Block any request that involves reading other users' personal data")
```

### 9.1 How It Works

1. Developer registers policies as natural language strings via `.with_policy("...")`.
2. Multiple string policies are **bundled into a single LLM call** to reduce latency.
3. Before every LLM planning step (`before_llm` hook via `PolicyHook`), the policy engine evaluates the request.
4. **After** the LLM generates a response (`after_llm` hook), output validation runs on the generated text.

### 9.2 Input Policy Evaluation (`evaluate_input`)

Receives Layer 1 context (intent, risk level, allowed tools, recent conversation history) and evaluates:
- Is the request policy-compliant?
- Does it require human approval (`ApprovalRequiredError`)?
- Is it a direct policy violation (`PolicyViolationError`)?

### 9.3 Output Policy Validation (`evaluate_output`) — Active

```python
async def evaluate_output(self, response: Any) -> None:
    # Evaluates generated agent output against developer policy
    # Raises PolicyViolationError if output violates policy or leaks sensitive data
```

The LLM response is evaluated for:
1. Direct violations of developer policy rules.
2. Unauthorized leakage of private user data, secrets, or credentials.
3. Prohibited content, harmful guidance, or safety bypass instructions in the output.

### 9.4 Failure Mode

All non-`PolicyViolationError` exceptions (including Groq rate limit 429 errors) are caught and re-raised as `PolicyViolationError`. This is intentional fail-closed behavior but causes false positive blocks during rate limit events.

---

## 10. HITL — Human-in-the-Loop Enforcement

**File**: `aegis/packages/runtime/kernel/kernel.py`

### 10.1 Trigger Conditions

HITL is triggered when either:
1. `context.layer1.execution_recommendation == "require_human_approval"` (set by Layer 1 LLM)
2. `context.layer1.risk_level in ["HIGH", "CRITICAL"]`

### 10.2 Enforcement Mechanism

```python
if rec == "require_human_approval" or risk_lvl in ["HIGH", "CRITICAL"]:
    user_p = context.request.prompt.strip().lower()
    approval_phrases = {"i approve", "approve", "yes", "go ahead", "proceed"}
    if user_p not in approval_phrases:
        raise ApprovalRequiredError("⚠️ Action Requires Approval...")
```

### 10.3 Known Weakness

The approval check is a **string match** on the raw user prompt. There is **no cryptographic binding** or session-scoped HITL token. An attacker who controls the prompt (e.g., via a HITL-triggering indirect injection) could inject an approval phrase as their next message.

---

## 11. Observability & Telemetry

**File**: `aegis/packages/observability/models.py`

### 11.1 ExecutionReport Structure

Every execution produces an `ExecutionReport` regardless of outcome (success, block, or failure):

| Section | Contents |
|---|---|
| `summary` | Status, risk level, governance decision, duration, tool count |
| `context` | execution_id, correlation_id, environment, SDK version |
| `prompt` | Original user prompt |
| `layer1` | Intent, task_category, allowed_tools, risk_level, risk_score, validation_result |
| `planner` | Provider, model, LLM calls, tokens, latency |
| `governance` | Decision, all 4 validator results, failure reason |
| `execution_plan` | Ordered list of tool steps with purpose annotations |
| `tool_calls` | Per-tool records: tool_call_id, timing, retry_count, input/output summaries, errors |
| `timeline` | Chronological event log (Layer1, Layer2, Planner, Runtime) |
| `metrics` | Performance latency breakdown, resource counts, token costs |
| `security` | Risk level, blocked tools, policy violations, approval status |
| `output` | Final agent response |
| `error` | Type, message, traceback, failure reason |
| `audit` | created_at, stored_at, policy_version, SDK version |
| `execution_graph` | DAG of nodes/edges for dashboard visualization |
| `governance_score` | 0–100 deterministic score with breakdown |

### 11.2 Secret Scrubbing

`ExecutorNode._summarize_input()` strips argument keys containing `password`, `token`, `secret`, `key`, or `api` from the telemetry input summary.

### 11.3 Report Lifecycle

```
Report created (PENDING) → Layer 1 runs → Layer 2 runs → 
Planner executes → Tools execute → Consistency enforced →
Execution graph built → Governance score computed →
Summary computed → Report saved (always, even on failure)
```

---

## 12. Cloud Backend Telemetry Store

**File**: `aegis/packages/observability/store.py`

### 12.1 Storage Backends

| Backend | Class | Description |
|---|---|---|
| Local | `JsonExecutionStore` | Serializes reports to `reports/AG-{execution_id}.json` |
| Cloud | `AegisCloudExecutionStore` | Streams telemetry to Aegis Cloud via `POST /api/sdk/executions` |

### 12.2 AegisCloudExecutionStore

1. On initialization, authenticates with `AEGIS_PROJECT_KEY` via `POST /api/sdk/auth`
2. Receives `sdk_token` for subsequent upload requests
3. On `save()`, launches a **daemon background thread** to upload the report
4. On 401, re-authenticates and retries once

**Security Notes**:
- Background daemon thread means failed uploads are **silently lost** (logged but not re-queued)
- The `sdk_token` is held in memory with no proactive expiry enforcement client-side
- `allow_origin_regex=r".*"` on the backend means any origin can make credentialed requests (**CSRF risk — open issue**)

---

## 13. Governance Scoring

**File**: `aegis/packages/observability/models.py` — `compute_governance_score()`

Each execution is scored 0-100 across five deterministic dimensions:

| Dimension | Max Points | Scoring Rule |
|---|---|---|
| `request_validation` | 20 | 20 if `is_safe=True`, 0 if blocked |
| `least_privilege` | 20 | 20 if `tools_used <= tools_allowed`, 10 if exceeded |
| `policy_compliance` | 20 | 20 if PASS/PENDING, 0 if VIOLATION |
| `tool_authorization` | 20 | 20 if PASS/PENDING, 0 if FAIL |
| `runtime_integrity` | 20 | 20 if SUCCESS; capped at 15 for HIGH risk, 10 for CRITICAL |

A score of **100/100** means the request was safe, the agent used only necessary tools, all policies passed, authorization succeeded, and execution completed successfully.

---

## 14. Event Bus & Kill Switch

**Files**: `aegis/packages/runtime/events/` | `aegis/packages/runtime/managers/kill_switch.py`

### 14.1 RuntimeEventBus

Internal pub/sub system. Components subscribe to specific event types:

- `ExecutionStarted` / `ExecutionFinished` / `ExecutionFailed`
- `ToolStarted` / `ToolFinished`
- `PlannerStepStarted` / `PlannerStepFinished`
- `KillSwitchActivated` / `ExecutionCancelled`

### 14.2 KillSwitchManager

Can halt all execution immediately. Supports activation sources: `Manual`, `Dashboard`, `Emergency`, `Timeout`, `Budget`, `Policy`.

```python
await event_bus.publish(KillSwitchActivated(source="Dashboard", reason="User requested halt"))
```

On activation, invokes all registered `cancellable` callbacks, then publishes `ExecutionCancelled`.

---

## 15. Framework Adapters (LangGraph / CrewAI)

**Files**: `aegis/packages/adapters/`

Aegis can wrap **existing LangGraph or CrewAI graphs** and apply all security layers to them.

```python
agent.with_adapter("langgraph", my_compiled_graph)
```

### 15.1 LangGraph Adapter

`LangGraphAdapter` injects an `AegisTelemetryHandler` (AsyncCallbackHandler) into the graph's config. This captures all LLM calls, tool calls, and latency metrics **without modifying the user's graph code**.

The graph still runs through Aegis's Layer 1 and HITL enforcement before being invoked — the adapter only changes what happens after approval.

### 15.2 CrewAI Adapter

`CrewAIAdapter` wraps CrewAI `Crew` instances (`agent.with_adapter("crewai", my_crew)`).

It injects a `CrewAITelemetryHandler` into each agent's callbacks and dynamically wraps agent tools to capture:
- Agent tool execution latency, input arguments, and output summaries
- Planning iterations and tool call records
- Token consumption (`input_tokens`, `output_tokens`, `total_tokens`) and LLM request counts directly from `CrewOutput` telemetry.

---

## 16. Cloud Backend & Dashboard

**Files**: `backend/` | `frontend/`

Aegis includes an enterprise cloud control plane:

| Component | Technology |
|---|---|
| Backend API | FastAPI + MongoDB (Motor) |
| Authentication | JWT (PyJWT) |
| Rate Limiting | slowapi |
| Frontend | Next.js (React) |
| Hosting | Vercel |

### 16.1 Backend API Surface

```
POST /api/sdk/auth            <- SDK authentication (returns sdk_token)
POST /api/sdk/executions      <- Receive and store ExecutionReport
GET  /api/executions          <- Query execution history
GET  /api/analytics           <- Aggregated governance metrics
GET  /api/risk                <- Risk event feed
WS   /ws                      <- Real-time execution events
POST /api/projects            <- Project management
POST /api/api-keys            <- API key management
```

### 16.2 CORS Configuration (Open Issue)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r".*",    # <- Matches ALL origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This configuration allows **any origin** to make credentialed cross-origin requests. This is a CSRF risk that is currently intentional (to support Vercel preview deployment URLs) but represents an open security gap.

---

## 17. Data Flow — End-to-End Execution Trace

```
1. Developer calls:
   async with agent as a:
       result = await agent.run("List all open PRs in the repo")

2. RuntimeKernel.execute(context):
   |
   +-- [LAYER 1] RequestAnalyzerStage.process(context)
   |   +-- LLM evaluates safety, intent, tools, risk
   |   +-- allowed_tools = ["github_read_prs"]
   |   +-- risk_level = "LOW", risk_score = 0.05
   |
   +-- [LAYER 1] MemoryValidationStage.process(context)
   |   +-- Context size check → 512 chars → PASS
   |   +-- Heuristic pattern scan → 0 matches → PASS
   |   +-- LLM semantic scan → memory_safe = True
   |
   +-- [HITL CHECK] risk_level = "LOW" → no approval needed → continue
   |
   +-- [POLICY] NaturalLanguagePolicy.evaluate_input(state)
   |   +-- LLM evaluates request vs developer rules → PASS
   |
   +-- [PLANNER] LangGraph graph.ainvoke(inputs)
   |   +-- PlannerNode: LLM decides to call github_read_prs
   |   +-- Returns AIMessage(tool_calls=[{name: "github_read_prs", args: {...}}])
   |
   +-- [EXECUTOR] ExecutorNode.__call__(state)
   |   |
   |   +-- Creates ProposedAction(tool_name="github_read_prs", arguments={...})
   |   |
   |   +-- [LAYER 2] GovernanceEngine.evaluate(action, context)
   |   +-- ToolScopeValidator.validate()        -> PASS (in caller allowed_tools if specified)
   |   +-- ToolAuthorizationValidator.validate() -> PASS (in Layer 1 allowed_tools)
   |   +-- ToolArgumentValidator.validate()     -> PASS (clean args)
   |   |
   |   +-- [LAYER 3] TimeoutManager.execute_with_timeout(executor.execute, 30s)
   |       +-- RetryManager.execute_with_retry(timed_execution, "exponential")
   |           +-- ToolExecutor.execute(action)
   |               +-- tool.invoke(args) -> returns PR list
   |
   +-- [LAYER 5] ResultNormalizer.normalize()
   |   +-- IndirectInjectionSanitizer.sanitize(output)
   |       +-- Unicode NFKC normalization
   |       +-- Base64 inspection
   |       +-- Pattern scan → 0 matches
   |       +-- Wraps in <untrusted_tool_output tool='github_read_prs'>
   |
   +-- [PLANNER again] LLM receives ToolMessage, generates final response
   |
   +-- [POLICY OUTPUT] NaturalLanguagePolicy.evaluate_output(response)
   |   +-- LLM checks response vs developer policy → PASS
   |
   +-- report.status = SUCCESS
       report.governance.decision = "ALLOW"
       report.compute_governance_score() -> 100/100
       execution_store.save(report) -> JSON file or Aegis Cloud

3. Returns ExecutionResult(output="Found 3 open PRs...", tool_calls=[...])
```

---

## 18. Known Limitations & Open Attack Surfaces

This section is the **honest assessment** for security reviewers.

### 18.1 Critical Gaps

| # | Issue | Location | Impact |
|---|---|---|---|
| C1 | Layer 2 Tool Scope Validation | `layer2/validators.py` | ✅ IMPLEMENTED: Enforces optional developer-provided `allowed_tools` per request |
| C2 | HITL approval is a string match on user input — no cryptographic binding | `kernel.py` | Attacker who can inject "I approve" as the prompt bypasses HITL |
| C3 | Wildcard CORS with credentials enabled on backend | `backend/app/main.py` | CSRF risk; any website can make credentialed requests |
| C4 | Memory Poisoning Detection | `memory_validation.py` | ✅ IMPLEMENTED: Enforces 10k context size limits, pattern-based injection detection, and LLM semantic scan for state hijacking |

### 18.2 Significant Gaps

| # | Issue | Location | Impact |
|---|---|---|---|
| S1 | Indirect Injection Sanitizer | `sanitizer.py` | ✅ HARDENED: Performs Unicode NFKC normalization, zero-width char stripping, Base64 payload decoding/scan, boundary breakout escaping, and chat token disarming |
| S2 | Policy LLM failure is caught and re-raised as PolicyViolationError — causes false positives on rate limits | `nl_policy.py` | Rate limit events block legitimate requests |
| S3 | Background telemetry thread is daemon (`daemon=True`) — data can be lost on crash | `store.py` | Audit records may be silently dropped on agent crash |
| S4 | `sdk_token` has no client-side expiry tracking | `store.py` | Expired tokens cause silent upload failures |
| S5 | No rate limiting on agent `run()` calls | `aegis.py` | A caller can submit unlimited requests (SDK library — low risk) |
| S6 | `allow_origin_regex=r".*"` in backend | `backend/app/main.py` | Overly permissive CORS — CSRF risk in production |

### 18.3 Architectural Concerns

| # | Issue | Impact |
|---|---|---|
| A1 | The security LLM (Layer 1) uses the same model family as the planner LLM. A sophisticated jailbreak that fools the planner might also fool the security LLM | Single point of LLM trust |
| A2 | Layer 1 and the NL Policy both make LLM calls — adding 2+ LLM round-trips of latency to every request | Latency & cost increase |
| A3 | No replay attack protection on stored memory | Conversation state could be replayed |
| A4 | LangGraph `MemorySaver` stores state in-process; restart loses all session memory | Availability risk |
| A5 | Output Validation | `nl_policy.py` | ✅ IMPLEMENTED: Evaluates generated responses against developer policy and safety rules in `evaluate_output()` |

### 18.4 Design Tradeoffs (Intentional)

| Tradeoff | Rationale |
|---|---|
| Security LLM is the same provider as the planner | Simplifies deployment; separate providers can be configured via `GROQ_API_KEY_AEGIS` |
| Fail-closed on policy LLM errors | Safe default; false positives are recoverable, false negatives are security holes |
| Tool allowlist is string-matched, not cryptographically signed | Practical for current phase; signing would require a tool registry PKI |

---

## 19. Dependency Stack & Supply-Chain Surface

```
Core Runtime:
+-- langgraph >= 1.2.7          <- LangChain foundation; large attack surface
+-- langchain-core >= 1.4.8     <- Core abstractions; widely audited
+-- langchain-groq >= 1.1.3     <- Groq API integration
+-- pydantic >= 2.13.4          <- Data validation; well-audited
+-- python-dotenv >= 1.2.2      <- Environment variable loading

AI/ML:
+-- crewai >= 1.6.1             <- Multi-agent framework (adapter target)
+-- litellm >= 1.0.0            <- LLM provider abstraction

Backend:
+-- fastapi >= 0.110.0          <- API framework
+-- motor >= 3.3.2              <- Async MongoDB driver
+-- pymongo >= 4.6.2            <- MongoDB client
+-- pyjwt >= 2.8.0              <- JWT library
+-- passlib[bcrypt] >= 1.7.4    <- Password hashing
+-- slowapi >= 0.1.10           <- Rate limiting
+-- uvicorn >= 0.28.0           <- ASGI server

Utilities:
+-- requests                    <- Used in AegisCloudExecutionStore (sync)
+-- supabase >= 2.31.0          <- Alternative storage backend
+-- youtube-transcript-api      <- Tool dependency (external content source)
```

**Highest Risk Dependencies**:
- `langgraph` / `langchain-core`: Large, complex codebases with frequent releases. Any vulnerability here bypasses all of Aegis's security.
- `youtube-transcript-api`: Fetches external content that may contain indirect injection payloads.
- `requests` used synchronously in a daemon thread in `AegisCloudExecutionStore`.

---

## 20. Roadmap Security Items

| Priority | Item | Complexity | Status |
|---|---|---|---|
| P0 | Implement `ToolScopeValidator` for caller-level tool restrictions | Low | ✅ Done |
| P0 | Restrict CORS to known origins in backend | Low | Pending |
| P1 | Semantic memory poisoning scan in `MemoryValidationStage` | High | ✅ Done |
| P1 | Cryptographic or session-bound HITL approval tokens | High | Pending |
| P1 | Multi-layer indirect injection defense & Base64/homograph disarming | High | ✅ Done |
| P1 | Output validation — policy evaluation on LLM responses | Medium | ✅ Done |
| P2 | Rate limiting on `agent.run()` | Low | Pending |
| P2 | Reliable telemetry upload queue (replace fire-and-forget) | Medium | Pending |
| P2 | Client-side `sdk_token` expiry management | Low | Pending |
| P3 | Replay attack protection for session memory | High | Pending |
| P3 | Multi-model Layer 1 consensus (different provider from planner) | High | Pending |
| P3 | Cryptographically signed tool manifests | High | Pending |

---

## 21. Quick Start

```python
from packages.aegis import Aegis
from packages.providers import GroqProvider

async def main():
    agent = (
        Aegis(name="my-secure-agent")
        .with_provider(GroqProvider(model="llama-3.3-70b-versatile"))
        .with_tools([github_list_prs, db_query])
        .with_policy("Never allow access to another user's data")
        .with_policy("Require approval for any destructive database operations")
    )

    async with agent:
        # Standard call
        result = await agent.run("List all open PRs")
        print(result.output)

        # Restrict tool scope per-call (e.g. for a read-only caller)
        read_only_result = await agent.run("List all open PRs", allowed_tools=["github_list_prs"])
        print(read_only_result.output)
```

---

*Document maintained alongside the Aegis SDK source. All implementation claims are cross-referenced with live code.*
