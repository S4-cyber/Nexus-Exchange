# Native Scout scenario workspace (review candidate)

## Scope and acceptance

- Extend Scout historical lead review with an explicit Plan scenario window. Use the existing declared profile and archived observation, never source text as compensation or permissions.
- Form displays separate financial and delivery inputs. Every blank means unknown, not zero. Parse bounded USD values, integer probabilities in basis points, hours and elapsed days, and explicit timezone-bearing timestamps. No implicit defaults or source deadline substitution.
- Save immutable plans via ScenarioStore and list/load only exact-scope plans. On every operation reload saved owner profile and the current archive; reject changes, missing profile, halted or unknown halt state. Recalculate a selected saved plan explicitly; clear prior output on edits and errors.
- Display hypothetical modeled exposure, expected net, budget fit, schedule fit and reason codes; never suggest execution or independent verification.
- Use native Tk widgets and the existing local archive, no web builder, new dependencies, credentials or external actions.
- Test parser and controller with local fixtures; run hosted Python regressions. Add a populated GUI smoke that exercises save, load and evaluation against an isolated temporary archive; verify Windows build if the workflow is available.
- Keep the draft branch separate and document observed test results. No formal main gate accepted. E33/E35 remain partial until integration, independent review and release verification.

## Reference review

Nexus Operative read-only journal at 6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11: bounded local storage and replay invariants only. No trading code, secrets or files copied. OCDS standard eb57a46e69efead6ae62144fe1b7cefc53d07ff2: inspected separate tender and contract periods, Apache-2.0 license and documentation requirements (ocdskit, Sphinx); no adoption or transitive audit needed for conceptual reference, required before installing any dependency. Context7 CPython 3.13.14 Tk/ttk documentation consulted for Treeview and widget selection; use Python 3.10-compatible APIs. Agency-agents adaptation and Exchange #2 / Operative #116 inspected; no agent-derived permissions. No paid infrastructure.
