import os
import json
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# I'm using gpt-4o-mini here to keep my simulation costs low.
MODEL = "gpt-4o-mini"

async def simulate_call(call_id: str, transcript_data: dict, prompt_text: str):
    print(f"\\n--- Simulating {call_id} ---")
    
    # I extract the customer's text to use as the simulator's input feed
    customer_messages = []
    for turn in transcript_data.get("transcript", []):
        if turn.get("speaker") == "customer":
            customer_messages.append(turn.get("text"))
            
    # Inject my prompt variables based on the customer data
    context = transcript_data.get("customer", {})
    # Inject variables into the prompt
    filled_prompt = prompt_text.replace("{{customer_name}}", context.get("name", "Customer"))
    filled_prompt = filled_prompt.replace("{{tos}}", context.get("pending_amount", "X"))
    filled_prompt = filled_prompt.replace("{{pos}}", context.get("closure_amount", "Y"))
    filled_prompt = filled_prompt.replace("{{settlement_amount}}", context.get("settlement_amount", "Z"))
    filled_prompt = filled_prompt.replace("{{dpd}}", str(context.get("dpd", "180")))
    # dummy variables for the rest
    for k in ["pending_amount", "due_date", "today_date", "today_day", "loan_id"]:
        filled_prompt = filled_prompt.replace("{{" + k + "}}", "Unknown")
        
    messages = [
        {"role": "system", "content": filled_prompt}
    ]
    
    simulated_transcript = []
    
    # 1. Trigger my agent's initial outbound greeting
    messages.append({"role": "user", "content": "[CALL CONNECTED - You are speaking first]"})
    
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=200,
            temperature=0.3
        )
        agent_reply = resp.choices[0].message.content
        simulated_transcript.append({"speaker": "agent_new", "text": agent_reply})
        messages.append({"role": "assistant", "content": agent_reply})
        print(f"Agent (New): {agent_reply}")
    except Exception as e:
        print(f"Error on init: {e}")
        
    # 2. Iterate through the transcript and replay each customer message sequentially
    for msg in customer_messages:
        print(f"Customer   : {msg}")
        simulated_transcript.append({"speaker": "customer", "text": msg})
        
        # User message to the API
        messages.append({"role": "user", "content": msg})
        
        # I truncate the history window here so I don't blow past context limits on long loops
        if len(messages) > 15:
            # keep system prompt, drop oldest chat pairs
            messages = [messages[0]] + messages[-14:]
            
        try:
            await asyncio.sleep(0.5)  # small buffer between turns
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=200,
                temperature=0.3
            )
            agent_reply = resp.choices[0].message.content
            simulated_transcript.append({"speaker": "agent_new", "text": agent_reply})
            messages.append({"role": "assistant", "content": agent_reply})
            print(f"Agent (New): {agent_reply}")
            
        except Exception as e:
            print(f"API Error during turn: {e}")
            agent_reply = "[API Limit Exceeded or Error]"
            simulated_transcript.append({"speaker": "agent_new", "text": agent_reply})
            await asyncio.sleep(10) # backoff
            
    return simulated_transcript

async def main():
    target_calls = ["call_07", "call_09"]
    base_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(base_dir, "../results")
    os.makedirs(results_dir, exist_ok=True)

    with open(os.path.join(base_dir, "../system-prompt.md"), "r") as f:
        original_prompt = f.read()
    with open(os.path.join(base_dir, "../system-prompt-fixed.md"), "r") as f:
        fixed_prompt = f.read()

    comparisons = []

    for cid in target_calls:
        with open(os.path.join(base_dir, f"../transcripts/{cid}.json"), "r") as f:
            data = json.load(f)

        print(f"\n=== Simulating {cid} with ORIGINAL prompt ===")
        old_transcript = await simulate_call(cid, data, original_prompt)

        print(f"\n=== Simulating {cid} with FIXED prompt ===")
        new_transcript = await simulate_call(cid, data, fixed_prompt)

        # Sample first 5 agent turns for the JSON comparison
        old_sample = [t for t in old_transcript if t["speaker"] == "agent"][:5]
        new_sample = [t for t in new_transcript if t["speaker"] == "agent_new"][:5]

        comparisons.append({
            "call_id": cid,
            "old_response_sample": old_sample,
            "new_response_sample": new_sample,
            "note": "Full before/after in results/{cid}_comparison.md"
        })

        # Save markdown comparison
        md_path = os.path.join(results_dir, f"{cid}_comparison.md")
        with open(md_path, "w") as f:
            f.write(f"# Before/After Simulation: {cid}\n\n")
            f.write("## Original Agent\n")
            for t in data.get("transcript", []):
                f.write(f"**{t.get('speaker').title()}**: {t.get('text')}\n\n")
            f.write("---\n## Fixed Agent\n")
            for t in new_transcript:
                f.write(f"**{t.get('speaker', '').title()}**: {t.get('text')}\n\n")
        print(f"Saved markdown comparison to {md_path}")

    # Save comparisons.json to results/
    comparisons_path = os.path.join(results_dir, "comparisons.json")
    with open(comparisons_path, "w") as f:
        json.dump(comparisons, f, indent=2)
    print(f"Saved comparisons to {comparisons_path}")

if __name__ == "__main__":
    asyncio.run(main())
