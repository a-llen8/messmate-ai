"""
MessMate — Complaint Text Pool Generator

ONE-TIME (cached) script that fixes the complaint-clusterer blocker:
scripts/generate_synthetic_data.py previously reused only 5 fixed
template strings x 3 meal slots = 15 unique complaint texts across
1,332+ complaint rows, which gives BERTopic / clustering nothing to
find structure in.

This script asks Gemini to paraphrase each of the 5 base templates,
per meal slot, into ~18 realistic variations (different tone, length,
specificity — some terse, some ranty, some polite) and caches the
result to scripts/data/complaint_pool.json.

generate_synthetic_data.py then samples from this pool instead of
reusing the 15 fixed strings.

HOW TO RUN (same pattern as generate_synthetic_data.py)
    cd backend
    venv\\Scripts\\activate
    python ..\\scripts\\generate_complaint_pool.py

Re-running is safe and free: if scripts/data/complaint_pool.json
already exists, the script does nothing and exits. Pass --force to
regenerate (this calls the Gemini API again — 15 calls total, one
per template x slot combination).
"""

import sys
import os
import json
import time
import argparse
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv

# project root .env (matches the path fix already applied in
# train_attendance_model.py — .env lives at messmate-ai/.env, not
# backend/.env)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from google import genai

# ── Config ──────────────────────────────────────────────────────
SLOTS = ["breakfast", "lunch", "dinner"]

# same 5 base templates currently in generate_synthetic_data.py
BASE_TEMPLATES = [
    "The {slot} today was undercooked and not up to the usual standard.",
    "Found the {slot} portion size too small for the price.",
    "The serving area for {slot} was not clean today.",
    "Had to wait a long time to be served during {slot}.",
    "The {slot} tasted stale, please check the ingredients.",
]

VARIANTS_PER_TEMPLATE = 18
OUTPUT_PATH = Path(__file__).parent / "data" / "complaint_pool.json"

# Tried in order; the script uses whichever one actually works for your
# API key/project and reports which one that was. "gemini-flash-latest"
# is Google's self-updating alias (always points at their current
# recommended free-tier flash model), so it's tried first.
CANDIDATE_MODELS = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]

PROMPT_TEMPLATE = """You are generating synthetic training data for a hostel mess
complaint-clustering system. Below are 5 base complaints about {slot},
numbered 1-5.

1. "{t0}"
2. "{t1}"
3. "{t2}"
4. "{t3}"
5. "{t4}"

For EACH of the 5 base complaints, write {n} different student complaint
messages that express the SAME underlying issue as that base complaint,
but with realistic variety:
- vary length (some one short sentence, some two sentences)
- vary tone (some terse/annoyed, some polite, some frustrated/ranty)
- vary specificity (some vague, some mention a specific detail like a
  dish name, a time, or how many days in a row)
- vary phrasing and word choice completely — do not just swap a
  synonym or two
- keep them realistic, like actual messages a college hostel student
  would type into a complaint box
- do not include quotation marks, numbering, or bullet points inside
  the text itself

Respond with ONLY a JSON object with keys "1" through "5", where each
value is a JSON array of {n} strings for that base complaint. No
markdown fences, no preamble, no other text.
"""


def generate_variants_for_slot(client, slot: str, templates: list[str], n: int, working_model: list) -> list[str]:
    """One API call covers all 5 base templates for a slot.
    working_model is a 1-element list used as a mutable pointer: once a
    model succeeds, it's reused directly for the remaining slots instead
    of re-trying the whole candidate list each time.
    """
    filled = [t.format(slot=slot) for t in templates]
    prompt = PROMPT_TEMPLATE.format(
        slot=slot, t0=filled[0], t1=filled[1], t2=filled[2], t3=filled[3], t4=filled[4], n=n,
    )

    models_to_try = [working_model[0]] if working_model[0] else CANDIDATE_MODELS
    last_error = None

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            text = response.text.strip()
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError(f"Unexpected response shape: {text[:200]}")

            all_variants = []
            seen = set()
            for key in ["1", "2", "3", "4", "5"]:
                group = parsed.get(key, [])
                for v in group:
                    v = v.strip()
                    if v and v not in seen:
                        seen.add(v)
                        all_variants.append(v)

            if working_model[0] != model_name:
                working_model[0] = model_name
                print(f"  (using model: {model_name})")
            return all_variants

        except Exception as e:
            last_error = e
            print(f"  {model_name} failed ({e}) — trying next candidate...")
            time.sleep(2)
            continue

    raise last_error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                         help="Regenerate even if complaint_pool.json already exists (calls Gemini again)")
    args = parser.parse_args()

    if OUTPUT_PATH.exists() and not args.force:
        print(f"{OUTPUT_PATH} already exists — nothing to do.")
        print("Pass --force to regenerate (this will call the Gemini API again).")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in environment / .env")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    pool = {slot: [] for slot in SLOTS}
    total_calls = len(SLOTS)
    call_num = 0
    working_model = [None]  # mutable pointer, filled in once a model succeeds

    for slot in SLOTS:
        call_num += 1
        print(f"[{call_num}/{total_calls}] {slot}: generating variants for all 5 base templates...")
        try:
            variants = generate_variants_for_slot(client, slot, BASE_TEMPLATES, VARIANTS_PER_TEMPLATE, working_model)
        except Exception as e:
            print(f"  ALL candidate models failed ({e}) — falling back to the 5 base template strings only")
            variants = [t.format(slot=slot) for t in BASE_TEMPLATES]
        print(f"  got {len(variants)} variants")
        pool[slot].extend(variants)
        time.sleep(2)  # be polite to the API

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2, ensure_ascii=False)

    print("\nDone.")
    for slot in SLOTS:
        print(f"  {slot}: {len(pool[slot])} unique complaint texts")
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
