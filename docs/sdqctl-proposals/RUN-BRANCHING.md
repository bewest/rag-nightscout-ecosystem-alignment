# Proposal: Conditional Branching for RUN Directive

> **Status**: Draft / Discussion  
> **Date**: 2026-01-22  
> **Author**: sdqctl development  
> **Scope**: Workflow control flow after RUN command success/failure

---

## Problem Statement

The `RUN` directive executes shell commands as mandatory checkpoints in workflows. Currently, when a command fails, the workflow either:
1. **Stops** (`RUN-ON-ERROR stop`) - preserves debugging context
2. **Continues** (`RUN-ON-ERROR continue`) - ignores the failure

Neither option allows the workflow to **adapt** based on the result. Users cannot:
- Ask the AI to fix failing tests before continuing
- Take different paths for success vs failure
- Implement retry-with-remediation patterns

---

## Design Tension

### sdqctl is NOT a Programming Language

sdqctl's ConversationFile format is intentionally declarative, inspired by Dockerfile. It describes **what** should happen, not **how** to handle every edge case. Adding conditional branching risks:

1. **Complexity creep** - Where does it end? Loops? Variables? Functions?
2. **Debugging difficulty** - Control flow in declarative formats is hard to trace
3. **Competing with the AI** - The agent is better at dynamic decisions than static rules

### But We Already Have Conditional Logic

| Existing Feature | Conditional Behavior |
|------------------|---------------------|
| `RUN-ON-ERROR stop\|continue` | Binary branch on failure |
| `PAUSE` | Conditional on human review |
| `CHECKPOINT` | Conditional save points |
| `CONTEXT-OPTIONAL` | Conditional file inclusion |
| `VALIDATION-MODE` | Conditional strictness |
| Loop detection | Conditional abort |
| `--max-cycles` | Conditional termination |

The precedent exists. The question is: **where to draw the line?**

---

## Options

### Option A: Do Nothing (Status Quo)

Keep `RUN-ON-ERROR stop|continue`. Complex conditional logic belongs in the prompt itself:

```dockerfile
PROMPT |
  Run `npm test`. If tests fail, analyze the errors and fix them.
  Keep iterating until all tests pass or you've tried 3 times.
```

**Pros:**
- No new syntax
- AI handles dynamic decisions
- Keeps ConversationFile simple

**Cons:**
- Relies on AI to interpret instructions correctly
- No structured checkpoint on failure
- Can't inject different context based on result

---

### Option B: Simple ON-FAILURE/ON-SUCCESS Blocks

Add optional blocks after RUN that execute based on result:

```dockerfile
RUN npm test
ON-FAILURE
  PROMPT Analyze test failures and propose fixes.
  CHECKPOINT test-failure
ON-SUCCESS
  PROMPT Tests passed. Generate coverage report.

PROMPT Continue with deployment...
```

**Semantics:**
- `ON-FAILURE` block executes only if RUN exits non-zero
- `ON-SUCCESS` block executes only if RUN exits zero
- Both blocks are optional
- After the block, workflow continues normally
- Nested RUN commands NOT allowed in blocks (no recursion)

**Pros:**
- Clear, limited scope
- Common use case (test → fix → retry)
- No new control flow primitives

**Cons:**
- Still adds conditional complexity
- Block scoping rules needed
- What about ON-FAILURE inside ON-FAILURE?

---

### Option C: Labeled Sections with GOTO

Allow jumping to named sections:

```dockerfile
SECTION main
  RUN npm test
  RUN-ON-ERROR goto fix-tests
  PROMPT Deploy the application.
  END

SECTION fix-tests
  PROMPT Analyze and fix test failures.
  RUN npm test
  RUN-ON-ERROR goto give-up
  GOTO main
  END

SECTION give-up
  PROMPT Tests still failing. Document issues for human review.
  PAUSE
  END
```

**Pros:**
- Full control flow
- Reusable sections
- Clear structure

**Cons:**
- **This is a programming language now**
- GOTO considered harmful (1968 called)
- Significantly harder to reason about
- Debugging nightmare

**Recommendation: Reject this option.**

---

### Option D: External Orchestration

Keep ConversationFile simple. Complex branching happens outside:

```bash
#!/bin/bash
sdqctl run test-phase.conv
if [ $? -ne 0 ]; then
  sdqctl run fix-tests.conv
  sdqctl run test-phase.conv  # retry
fi
sdqctl run deploy-phase.conv
```

Or with `sdqctl flow`:

```yaml
# workflow.yaml
phases:
  - name: test
    conv: test-phase.conv
    on_failure: fix-tests
  - name: fix-tests
    conv: fix-tests.conv
    next: test
  - name: deploy
    conv: deploy-phase.conv
```

**Pros:**
- ConversationFile stays declarative
- Full power of shell/YAML for orchestration
- Separation of concerns

**Cons:**
- Two files to maintain
- Context doesn't flow naturally between phases
- More complex setup

---

### Option E: AI-Driven Retry with Limits

Add `RUN-RETRY` directive that asks AI to fix issues:

```dockerfile
RUN npm test
RUN-RETRY 3 "Fix the failing tests based on error output"

# Equivalent to:
# - Run npm test
# - If fails, send error output + retry prompt to AI
# - AI makes fixes
# - Run npm test again
# - Repeat up to 3 times
# - If still failing after 3 tries, use RUN-ON-ERROR behavior
```

**Pros:**
- Single directive, clear intent
- Leverages AI for the fix (not static rules)
- Built-in limit prevents infinite loops
- Common pattern made easy

**Cons:**
- Magic behavior (multiple AI turns hidden)
- Token consumption not obvious
- What if AI needs to run OTHER commands to fix?

---

## Recommendation

**Start with Option E (RUN-RETRY)** as it:
1. Addresses the most common use case (test → fix → retry)
2. Leverages AI instead of static control flow
3. Has built-in safety (retry limit)
4. Minimal syntax addition

**Defer Option B (ON-FAILURE/ON-SUCCESS)** until we have more use cases that Option E doesn't cover.

**Reject Option C (GOTO)** entirely.

---

## Alternative: Let the Quine Pattern Handle It

The existing quine workflow pattern already handles adaptive behavior:

```dockerfile
# test-and-fix.conv
PROLOGUE @progress.md

PROMPT |
  Review the test status in progress.md.
  If tests are failing, analyze and fix one issue.
  If tests are passing, mark complete.
  Update progress.md with current status.

EPILOGUE @progress.md
```

Run with `sdqctl cycle --max-cycles 10`. The workflow adapts based on the progress file contents, not static branching.

**This may be the right answer**: complex conditional logic belongs in the prompt + state file pattern, not new directives.

---

## Questions for Discussion

1. **Is RUN-RETRY sufficient?** Or do we need full ON-FAILURE blocks?

2. **Should branching be in ConversationFile at all?** Maybe `sdqctl flow` (YAML) is the right place.

3. **How do we prevent complexity creep?** If we add ON-FAILURE, what's next?

4. **Token visibility**: How do we make clear that RUN-RETRY might consume N × tokens?

5. **Interaction with CHECKPOINT**: Should ON-FAILURE auto-checkpoint?

---

## Implementation Notes (if approved)

### RUN-RETRY Implementation

```python
class RunRetryDirective:
    max_retries: int
    retry_prompt: str
    
    async def execute(self, session, runner):
        for attempt in range(self.max_retries + 1):
            result = await runner.run_command(self.command)
            if result.success:
                return result
            if attempt < self.max_retries:
                # Send error to AI with retry prompt
                prompt = f"{self.retry_prompt}\n\nError output:\n{result.stderr}"
                await session.send(prompt)
        return result  # Final failure
```

### ON-FAILURE Block Implementation

```python
class RunDirective:
    on_failure: list[Directive]  # Optional block
    on_success: list[Directive]  # Optional block
    
    async def execute(self, session, runner):
        result = await runner.run_command(self.command)
        if result.success and self.on_success:
            for directive in self.on_success:
                await directive.execute(session, runner)
        elif not result.success and self.on_failure:
            for directive in self.on_failure:
                await directive.execute(session, runner)
        return result
```

---

## References

- [Dockerfile best practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/) - "Keep it simple"
- [Make vs programming](https://www.gnu.org/software/make/manual/html_node/Conditionals.html) - Even Make has conditionals
- [GitHub Actions conditionals](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_idif) - `if:` on steps
- [Quine patterns in sdqctl](./docs/QUINE-WORKFLOWS.md) - Existing adaptive approach

---

**Feedback requested.** Please comment on which option best fits sdqctl's philosophy.
