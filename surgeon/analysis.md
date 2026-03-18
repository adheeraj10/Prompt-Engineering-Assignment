# Surgeon Analysis: Flaws in the Original System Prompt

Based on the evaluation of the 10 transcripts and the human verdicts in `verdicts.json`, we can definitively trace the failures of the worst calls back to specific missing logic or flawed instructions in `system-prompt.md`.

## Flaw 1: Missing Language Switch Triggers & Fallbacks
**Proof:** `call_02` and `call_07`
**Analysis:** The original prompt provides a `switch_language` function but zero instructions in the Global or Phase contexts on *when* or *how* to use it. 
- In `call_02`, the customer repeatedly asks to speak in Hindi, but the agent fails to switch promptly, continuing to output English tokens while trying to apologize.
- In `call_07`, there is a language barrier (Tamil). The agent attempts a few words but has no fallback strategy (e.g., escalating to a human, or ending the call politely if translation confidence is low), resulting in a dead end.

## Flaw 2: Forced Outbound Context & Missing Callback Awareness
**Proof:** `call_09`
**Analysis:** The prompt hardcodes the assumption that every call is a cold outbound attempt. Phase 1 explicitly states: *A greeting has ALREADY been spoken. The borrower heard: "Hello, this is Alex..."*. 
- In `call_09`, the customer is calling *back* (inbound context). Because the agent is forced into an outbound state-machine flow, it completely fails to adapt to the customer's opening context. The agent stubbornly proceeds as if it initiated the call.

## Flaw 3: Loop Escapes & Over-eager Thresholds
**Proof:** `call_03` and `call_10`
**Analysis:** The prompt's infinite loop handling is broken in two contradictory ways:
1. **No Escalation for "Already Paid" Claims:** In `call_03`, the customer claims they already paid. The prompt says to collect details and call `end_call` with reason `claims_already_paid`. However, if the customer gets frustrated or the agent fails to parse the UTR, the agent just infinitely loops asking for the same details instead of gracefully escalating or ending the call on a frustrated threshold.
2. **Premature Dismissal:** In `call_10`, the agent encounters an evasive customer. Instead of probing deeper, the prompt's instruction (`DO NOT GET STUCK: After 5-6 genuinely circular exchanges, move to closing`) combined with poor digging instructions causes the agent to just give up entirely, resulting in an "Extremely short call". 

## The Fix Strategy
We will rewrite the system prompt (`system-prompt-fixed.md`) using strict **State-Machine logic** via XML tags.
1. **Language Rules:** Explicit triggers for `switch_language`, including a failsafe: "If the customer speaks a language you cannot confidently process, call `end_call` with reason `language_barrier`."
2. **Context Awareness:** Remove the forced Outbound assumption. Make Phase 1 branch based on whether the customer initiated (Inbound) or agent initiated (Outbound).
3. **Escalation & Probing:** Add an `escalate_to_human` function or explicit graceful exit for looped frustrations. Add deep-probing constraints for evasive answers ("If customer gives 1-word answers, ask an open-ended question about their financial change").
