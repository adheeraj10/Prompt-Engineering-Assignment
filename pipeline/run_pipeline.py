import os
import sys
import json
import asyncio
import argparse
from openai import AsyncOpenAI
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from surgeon.simulator import simulate_call
from detective.evaluator import evaluate_transcript, CallEvaluation, load_cache
from pipeline.aggregator import compute_summary, save_summary

load_dotenv()
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

META_PROMPT = """You are an expert Prompt Engineer for an AI debt collection agent.
Your objective is to fix a system prompt that caused the agent to fail its QA evaluation.

Here is the CURRENT SYSTEM PROMPT:
==================================
{prompt_text}
==================================

The agent ran a simulated call and scored {score}/100.
Here is the evaluator's CHAIN OF THOUGHT:
{chain_of_thought}

Here are the WORST MESSAGES the agent generated:
{worst_messages}

YOUR TASK: Output a complete, updated, and highly improved SYSTEM PROMPT that fixes these exact failures.
Ensure you keep the state-machine structure but add robust constraints/rules to prevent the mistakes noted above.
DO NOT wrap the output in any preamble or markdown code blocks (e.g. no ```markdown), just output the raw prompt text directly.
"""

async def auto_optimize_prompt(prompt_text: str, eval_result: CallEvaluation) -> str:
    print(f"\n--- [AUTO-OPTIMIZER] Triggered (Score: {eval_result.score}/100) ---")

    worst_msgs_str = "\n".join(
        [f"- turn {m.turn_index}: '{m.text}' (Reason: {m.reason_why_bad})" for m in eval_result.worst_messages]
    )
    formatted_prompt = META_PROMPT.format(
        prompt_text=prompt_text,
        score=eval_result.score,
        chain_of_thought=eval_result.chain_of_thought,
        worst_messages=worst_msgs_str
    )

    try:
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": formatted_prompt}],
            temperature=0.2,
            max_tokens=3000
        )
        new_prompt = resp.choices[0].message.content.strip()
        # Strip markdown code fences if the model added them
        for fence in ["```markdown", "```"]:
            if new_prompt.startswith(fence):
                new_prompt = new_prompt[len(fence):].strip()
        if new_prompt.endswith("```"):
            new_prompt = new_prompt[:-3].strip()
        return new_prompt
    except Exception as e:
        print(f"Auto-optimizer failed: {e}")
        return prompt_text

async def run_pipeline(prompt_path: str, transcripts_dir: str, auto_optimize: bool = False):
    print("\n=== Running Pipeline ===")

    with open(prompt_path, "r") as f:
        prompt_text = f.read()

    transcript_files = sorted([
        os.path.join(transcripts_dir, f)
        for f in os.listdir(transcripts_dir)
        if f.endswith(".json") and "_manifest.json" not in f
    ])

    # I load my evaluation cache here so I don't burn API credits on unchanged transcripts
    cache = load_cache()
    all_results = []

    for transcript_path in transcript_files:
        call_id = os.path.basename(transcript_path).replace(".json", "")
        print(f"\n--- Processing {call_id} ---")

        with open(transcript_path, "r") as f:
            data = json.load(f)

        # 1. Simulate the conversation turn-by-turn
        print("\n[1/3] Simulating Call...")
        simulated_transcript = await simulate_call(call_id, data, prompt_text)

        sim_data = {**data, "transcript": simulated_transcript, "function_calls": [], "call_id": f"{call_id}_simulated"}
        tmp_path = f"./{call_id}_sim_tmp.json"
        with open(tmp_path, "w") as f:
            json.dump(sim_data, f)

        # 2. Pass the simulated transcript to my evaluator script
        print("\n[2/3] Evaluating Simulated Call...")
        eval_result = await evaluate_transcript(tmp_path, cache)
        all_results.append(eval_result.model_dump())

        print(f"\nEvaluation Verdict: {eval_result.verdict.upper()} (Score: {eval_result.score})")
        print(f"Reasoning: {eval_result.chain_of_thought}")

        # 3. If it failed, I let gpt-4o try rewriting the prompt for me (optional)
        if auto_optimize and eval_result.score < 100:
            print("\n[3/3] Auto-Optimizing Prompt...")
            new_prompt = await auto_optimize_prompt(prompt_text, eval_result)

            opt_path = os.path.join(os.path.dirname(prompt_path), "system-prompt-auto-optimized.md")
            with open(opt_path, "w") as f:
                f.write(new_prompt)
            print(f"Saved optimized prompt to {opt_path}")

            print("\n--- Re-simulating with Optimized Prompt ---")
            sim_opt = await simulate_call(call_id, data, new_prompt)
            sim_data["transcript"] = sim_opt
            with open(tmp_path, "w") as f:
                json.dump(sim_data, f)

            print("\n--- Re-evaluating Optimized Call ---")
            eval_opt = await evaluate_transcript(tmp_path, cache)
            print(f"\nNew Verdict: {eval_opt.verdict.upper()} (Score: {eval_opt.score})")
            print(f"New Reasoning: {eval_opt.chain_of_thought}")
            prompt_text = new_prompt
        else:
            print("\n[3/3] Auto-Optimize skipped.")

        # Cleanup my temp simulation file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    # Aggregate and save summary
    summary = compute_summary(all_results)
    summary_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "results",
        "results_summary.json"
    )
    save_summary(summary, summary_path)

    print("\n=== Pipeline Complete ===")
    print(f"Average score: {summary.get('avg_score')} | Good: {summary.get('good_count')} | Bad: {summary.get('bad_count')}")

async def main():
    parser = argparse.ArgumentParser(description="Run the AI Agent Evaluation Pipeline")
    parser.add_argument("--prompt", type=str, required=True, help="Path to the system prompt file")
    parser.add_argument("--transcripts", type=str, required=True, help="Path to the transcripts directory")
    parser.add_argument("--auto_optimize", action="store_true", help="Enable the auto-optimizer feature")
    args = parser.parse_args()

    await run_pipeline(args.prompt, args.transcripts, args.auto_optimize)

if __name__ == "__main__":
    asyncio.run(main())
