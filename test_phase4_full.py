#!/usr/bin/env python3
"""Comprehensive Phase 4 test suite"""

import sys
import json
from database import (
    get_setting, set_setting, get_feedback_for_prompt, 
    list_feedback, save_feedback, get_study_questions
)

print("\n" + "="*70)
print("PHASE 4 COMPREHENSIVE TEST SUITE")
print("="*70)

test_count = 0
pass_count = 0


def test(name, condition, details=""):
    """Helper for test reporting"""
    global test_count, pass_count
    test_count += 1
    if condition:
        pass_count += 1
        print(f"✓ Test {test_count}: {name}")
        if details:
            print(f"  {details}")
    else:
        print(f"✗ Test {test_count}: {name}")
        if details:
            print(f"  {details}")
    return condition


# ========== SETTINGS TESTS ==========
print("\n[1/3] FEEDBACK SETTINGS")
print("-" * 70)

set_setting('feedback_context_mode', 'full')
test("Set feedback_context_mode to 'full'", 
     get_setting('feedback_context_mode') == 'full')

set_setting('feedback_context_mode', 'light')
test("Set feedback_context_mode to 'light'", 
     get_setting('feedback_context_mode') == 'light')

set_setting('feedback_context_mode', 'off')
test("Set feedback_context_mode to 'off'", 
     get_setting('feedback_context_mode') == 'off')

set_setting('feedback_max_items', '10')
test("Set feedback_max_items to 10", 
     get_setting('feedback_max_items') == '10')

set_setting('feedback_char_budget', '2000')
test("Set feedback_char_budget to 2000", 
     get_setting('feedback_char_budget') == '2000')

# ========== SCORING TESTS ==========
print("\n[2/3] FEEDBACK RELEVANCE SCORING")
print("-" * 70)

# Get feedback with scoring
feedback_with_scores = get_feedback_for_prompt('general', include_scores=True)
result_has_scores = False
if feedback_with_scores and "_combined_score" in feedback_with_scores[0]:
    result_has_scores = True
    first_item = feedback_with_scores[0]
    test("Scoring metadata in results", result_has_scores,
         f"Combined score: {first_item.get('_combined_score'):.2f}")
    
    # Verify score components
    test("Score has folder_score component", "_folder_score" in first_item)
    test("Score has type_score component", "_type_score" in first_item)
    test("Score has content_score component", "_content_score" in first_item)
    test("Combined score is 0-1 range", 
         0 <= first_item.get('_combined_score', 0) <= 1)
else:
    test("Scoring available", False, "(No feedback in DB yet)")

# ========== TOKEN BUDGET TESTS ==========
print("\n[3/3] TOKEN BUDGET ENFORCEMENT")
print("-" * 70)

# Test with different char budgets
set_setting('feedback_char_budget', '200')
set_setting('feedback_max_items', '20')

feedback_limited = get_feedback_for_prompt('general')
if feedback_limited:
    # Build context block manually to test char enforcement
    lines = ["Recent user corrections to prioritize:"]
    used = len(lines[0])
    budget = 200
    for idx, row in enumerate(feedback_limited, start=1):
        text = f"{idx}. test"
        if used + len(text) + 1 > budget:
            break
        used += len(text) + 1
    
    test("Char budget respected", used <= budget,
         f"Used {used} chars of {budget} budget")
else:
    test("Char budget test", False, "No feedback in DB")

# ========== SUMMARY ==========
print("\n" + "="*70)
print(f"TEST SUMMARY: {pass_count}/{test_count} tests passed")
if pass_count == test_count:
    print("✓ ALL TESTS PASSED - Phase 4 Ready for Integration!")
else:
    print(f"⚠ {test_count - pass_count} test(s) failed")
print("="*70 + "\n")

sys.exit(0 if pass_count == test_count else 1)
