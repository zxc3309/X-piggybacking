# Step-by-Step Guide: Updating Your Match Prompt

## What You'll Fix

Based on your feedback analysis, your LLM has a **31% false positive rate** because it accepts posts that:
1. Just state numbers/metrics without insight (e.g., "OI is $8.2B, 45% growth")
2. Promise content but don't deliver (e.g., "overview of X...")

## Step 1: Start the Interactive Tool

Open your terminal and run:

```bash
cd /Users/billhsu/Documents/X_pickybacking/X-piggybacking
python3 scripts/update_prompt.py
```

## Step 2: Review Current Performance

You'll see:
```
======================================================================
CURRENT PROMPT: match_prompt
======================================================================
Version: v1.0

Prompt Text:
[Your current prompt displayed here]

======================================================================
RECENT PERFORMANCE
======================================================================
Accuracy: 69.0%
False Positive Rate: 31.0% ⚠ High  <-- This is what we need to fix!
False Negative Rate: 0.0% ✓

======================================================================
KEY INSIGHTS FROM FEEDBACK ANALYSIS
======================================================================
🔴 False Positives: 13 cases
   Common issues:
   • "just saying number and the growth, no implication, no insight"
   • "It's simply stating that it's an "overview" without any actual content."
```

## Step 3: Choose to Edit the Prompt

You'll see a menu:
```
WHAT WOULD YOU LIKE TO DO?
[1] Edit prompt (opens in editor)
[2] View recent disagreements
[3] Cancel

Choice (1-3):
```

**Type:** `1` and press Enter

## Step 4: Edit the Prompt

Your default text editor will open (usually `nano` or `vi`).

**Current prompt** (what you'll see):
```
Role: You are a Investor for a Crypto Liquid Fund. Your job is to strictly filter content.

Task: Evaluate the provided text and assign a binary classification code: 0 (Discard) or 1 (Keep).

Classification Logic:

Assign "1" (Relevant - Liquid Investment Signal) ONLY if the content:

Analyzes Market Structure: Mentions specific market dynamics such as supply–demand imbalances, liquidity depth, positioning, leverage, funding rates, open interest, or capital flows.

Connects Fundamentals to Price: Translates protocol metrics directly into price-relevant mechanisms (e.g., token emissions, unlock schedules, fee capture/burns, or incentive alignment).

Focuses on Asymmetry & Timing: Distinguishes between a "good project" and a "good trade." Look for discussions on entry/exit timing, risk/reward ratios, or specific invalidation points for a thesis.

Includes convincing thesis or data to support the narrative, not just a short market sentiment comment

Assign "0" (Irrelevant - Noise/VC/Retail) if the content:

Focuses primarily on "long-term vision," "team pedigree," or "changing the world" without discussing current market valuation or tradability.

Purely bullish beliefs or "HODL" narratives that ignore downside risk, liquidity constraints, or macro correlation.

Is Generic/Promotional: Basic educational content ("What is DeFi?") or blind promotion without a thesis based on the factors above.

Output: only contain 1/0
```

**What to add:** Find the section "Assign "0" (Irrelevant - Noise/VC/Retail) if the content:" and add these two new criteria:

```
Assign "0" (Irrelevant - Noise/VC/Retail) if the content:

Focuses primarily on "long-term vision," "team pedigree," or "changing the world" without discussing current market valuation or tradability.

Purely bullish beliefs or "HODL" narratives that ignore downside risk, liquidity constraints, or macro correlation.

Is Generic/Promotional: Basic educational content ("What is DeFi?") or blind promotion without a thesis based on the factors above.

States metrics, statistics, or numbers without analysis, implications, or investment thesis (e.g., "OI is $X billion" or "Y% growth" without explaining what it means or what action to take).  <-- ADD THIS

Promises or mentions analysis without providing it (e.g., "overview of X", "discussion about Y", "here's a thread on Z" without the actual analysis or insights).  <-- ADD THIS

Output: only contain 1/0
```

### If using `nano` editor:
1. Use arrow keys to navigate
2. Add the two new lines above
3. Press `Ctrl+O` to save
4. Press `Enter` to confirm
5. Press `Ctrl+X` to exit

### If using `vi` editor:
1. Press `i` to enter insert mode
2. Navigate and add the two new lines
3. Press `Esc` to exit insert mode
4. Type `:wq` and press Enter to save and quit

## Step 5: Preview Your Changes

After saving, you'll see:
```
======================================================================
NEW PROMPT PREVIEW
======================================================================
[First 200 characters of your new prompt]
======================================================================

Save this new prompt? (yes/no):
```

**Type:** `yes` and press Enter

## Step 6: Add Notes

You'll be asked:
```
Notes about changes (optional):
```

**Type something like:**
```
Added rejection criteria for posts that state metrics without insight and posts that promise analysis without delivering
```

Press Enter.

## Step 7: Choose Activation

You'll see:
```
🔧 Creating new prompt version...
✓ Created v1.1 (status: testing)

======================================================================
ACTIVATION OPTIONS
======================================================================
[1] Activate v1.1 now (will be used in next scrape)
[2] Keep as 'testing' (activate later)

Choice (1-2):
```

**Type:** `1` and press Enter

This will:
- Set v1.1 as active
- Archive v1.0
- Update the `prompt_inuse` worksheet with your new prompt
- Save your baseline metrics

## Step 8: Verify Success

You should see:
```
🔧 Activating v1.1...
✓ Archived previous active version: v1.0
✓ Set v1.1 status to 'active'
✓ Updated prompt_inuse with new prompt text

✅ SUCCESS! v1.1 is now active
   Next scrape will use the updated prompt

🔧 Calculating current metrics for tracking...
✓ Saved baseline metrics for v1.1
```

## Step 9: Test Your New Prompt

Now test if the new prompt works better:

```bash
# Run a scrape to test the new prompt
python3 -m x_auto.workflow.scrape_filter
```

Wait a few days, give feedback on new posts, then analyze again:

```bash
python3 scripts/analyze_feedback.py
```

**Expected improvement:** False positive rate should drop from 31% to around 15-20% or lower!

## Troubleshooting

**If your editor doesn't open:**
```bash
# Set nano as your default editor
export EDITOR=nano

# Then try again
python3 scripts/update_prompt.py
```

**If you make a mistake:**
```bash
# View all versions
python3 scripts/update_prompt.py --show-current

# Rollback to v1.0
python3 scripts/update_prompt.py --activate v1.0
```

**To compare versions later:**
```bash
python3 scripts/update_prompt.py --compare v1.0 v1.1
```

## Summary

1. Run: `python3 scripts/update_prompt.py`
2. Choose option `1` to edit
3. Add two new rejection criteria for metrics-without-insight and promise-without-delivery
4. Save in editor (Ctrl+O, Ctrl+X in nano)
5. Confirm save: `yes`
6. Add notes about changes
7. Activate: `1`
8. Test with a scrape run!

Your new v1.1 prompt should significantly reduce false positives! 🎉
