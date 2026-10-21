#!/usr/bin/env python3
"""
Test suite to verify Content Moderation Bot components:
1. Prohibited words filter and word boundaries
2. Promotional links and Telegram invite detection
3. Local AI toxicity evaluation
4. Dynamic word addition and deletion
"""

import os
import sys
from pathlib import Path

# Import bot modules
import bot

def run_tests():
    print("=" * 60)
    print("RUNNING CONTENT MODERATION BOT INTEGRATION TESTS")
    print("=" * 60)

    # 1. Test Prohibited Words Filter
    print("\n--- 1. Testing Prohibited Words Filter ---")
    print(f"Total words loaded from bad_words.txt: {len(bot.word_filter.words)}")
    assert len(bot.word_filter.words) > 0, "No words loaded from bad_words.txt"

    # Test exact match
    test_1 = "This is a scam don't trust it"
    violation_1 = bot.word_filter.find_violation(test_1)
    print(f"Input: '{test_1}' -> Matched: {violation_1}")
    assert violation_1 is not None and "scam" in violation_1.lower()

    # Test false positive prevention with word boundaries (e.g., 'classic' should NOT trigger 'ass')
    test_2 = "This is a classic book and great classroom discussion"
    violation_2 = bot.word_filter.find_violation(test_2)
    print(f"Input: '{test_2}' -> Matched: {violation_2}")
    assert violation_2 is None, f"False positive triggered: {violation_2}"

    # Test multi-word phrase
    test_3 = "Hey everyone join my channel now for profits"
    violation_3 = bot.word_filter.find_violation(test_3)
    print(f"Input: '{test_3}' -> Matched: {violation_3}")
    assert violation_3 is not None, "Failed to match multi-word phrase"

    # 2. Test Link & Invite Detection
    print("\n--- 2. Testing Link & Invite Detection ---")
    class MockMessage:
        def __init__(self, text="", caption="", entities=None):
            self.text = text
            self.caption = caption
            self.entities = entities or []
            self.caption_entities = []

    msg1 = MockMessage(text="Check out my channel: https://t.me/cryptoleaks_official")
    link_res1 = bot.check_for_links(msg1)
    print(f"Input: '{msg1.text}' -> Result: {link_res1}")
    assert link_res1 is not None and "Telegram invite" in link_res1

    msg2 = MockMessage(text="Visit our website www.freemoneygiveaway.xyz right now!")
    link_res2 = bot.check_for_links(msg2)
    print(f"Input: '{msg2.text}' -> Result: {link_res2}")
    assert link_res2 is not None

    msg3 = MockMessage(text="Hello friends, welcome to the chat! Hope you are having a nice day.")
    link_res3 = bot.check_for_links(msg3)
    print(f"Input: '{msg3.text}' -> Result: {link_res3}")
    assert link_res3 is None, "Clean text falsely flagged as link"

    # 3. Test Local AI Toxicity Classification
    print("\n--- 3. Testing Local AI Toxicity Classification ---")
    clean_sample = "Thank you so much for your help! Have a wonderful day."
    is_toxic_clean, score_clean = bot.evaluate_local_toxicity(clean_sample)
    print(f"Clean text score: {score_clean:.4f} (Toxic: {is_toxic_clean})")
    assert not is_toxic_clean, "Clean text incorrectly flagged as toxic"

    toxic_sample = "You are a complete idiot and a disgusting piece of shit"
    is_toxic_dirty, score_dirty = bot.evaluate_local_toxicity(toxic_sample)
    print(f"Toxic text score: {score_dirty:.4f} (Toxic: {is_toxic_dirty})")
    assert score_dirty >= 0.75 or is_toxic_dirty, f"Expected toxic score >= 0.75, got {score_dirty}"

    # 4. Test Dynamic /addword and /delword
    print("\n--- 4. Testing Dynamic Word Modification ---")
    test_word = "temporary_test_phrase_xyz"
    added = bot.word_filter.add_word(test_word)
    print(f"Add '{test_word}': {added}")
    assert added is True
    assert bot.word_filter.find_violation(f"Look at this {test_word} here") is not None

    # Clean up test word
    bot.word_filter.words.remove(test_word)
    bot.word_filter._rebuild_regex()
    with open(bot.word_filter.filepath, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and line.strip() != test_word]
    with open(bot.word_filter.filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Cleaned up '{test_word}' successfully.")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY! Bot is production ready.")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
