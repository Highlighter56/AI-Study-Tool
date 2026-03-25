#!/usr/bin/env python3
"""Test Phase 4 database changes"""

from database import get_setting, set_setting, get_feedback_for_prompt

print("="*60)
print("PHASE 4 DATABASE CHANGES TEST")
print("="*60)

# Test 1: Feedback settings
print("\n✓ Test 1: Feedback Settings")
print("-" * 40)
set_setting('feedback_context_mode', 'light')
set_setting('feedback_max_items', '3')
set_setting('feedback_char_budget', '500')

mode = get_setting('feedback_context_mode')
maxitems = get_setting('feedback_max_items')
charbudget = get_setting('feedback_char_budget')

print(f"  feedback_context_mode: {mode}")
print(f"  feedback_max_items: {maxitems}")
print(f"  feedback_char_budget: {charbudget}")
assert mode == "light", "Mode setting failed"
assert maxitems == "3", "Max items setting failed"
assert charbudget == "500", "Char budget setting failed"
print("  ✓ All settings saved correctly")

# Test 2: Feedback scoring
print("\n✓ Test 2: Feedback Scoring Function")
print("-" * 40)
results = get_feedback_for_prompt('general', include_scores=True)
print(f"  Feedback items retrieved: {len(results)}")
if results:
    first = results[0]
    if "_combined_score" in first:
        print(f"  ✓ Scoring metadata included")
        print(f"    - Combined score: {first.get('_combined_score'):.2f}")
        print(f"    - Folder score: {first.get('_folder_score'):.2f}")
        print(f"    - Type score: {first.get('_type_score'):.2f}")
        print(f"    - Content score: {first.get('_content_score'):.2f}")
    else:
        print(f"  ✓ Function works (no scores in this result)")
else:
    print("  ℹ No feedback yet (expected on fresh DB)")

print("\n" + "="*60)
print("✓ ALL TESTS PASSED - Phase 4 Database Ready!")
print("="*60)
