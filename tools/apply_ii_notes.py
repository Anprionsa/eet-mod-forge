#!/usr/bin/env python3
"""
Apply reviewed notes from ii_review.json to mods.json.

Filters for high-quality matches and clean note text only.
Resolves duplicate mod matches by picking the best doc entry per mod.

Usage: python tools/apply_ii_notes.py [--dry-run]
"""

import sys
import os
import json
import re
import difflib
from collections import defaultdict

def main():
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    dry_run = '--dry-run' in sys.argv

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    review_path = os.path.join(script_dir, 'ii_review.json')
    mods_path = os.path.join(project_dir, 'data', 'mods.json')

    with open(review_path, 'r', encoding='utf-8') as f:
        review = json.load(f)
    with open(mods_path, 'r', encoding='utf-8') as f:
        mods = json.load(f)

    mods_by_id = {m['i']: m for m in mods}

    # ── Step 1: Filter to high-confidence actionable items ──
    actionable = [
        item for item in review
        if item['action'] in ('add', 'merge')
        and item['match_confidence'] >= 0.90
        and item['mod_index'] is not None
        and item['classified_notes']  # must have at least one classified note
    ]
    print(f"Actionable items (conf >= 0.90, has notes): {len(actionable)}")

    # ── Step 2: Resolve duplicate mod_index matches ──
    # Group by mod_index, pick best match per mod
    by_mod = defaultdict(list)
    for item in actionable:
        by_mod[item['mod_index']].append(item)

    best_per_mod = {}
    for mod_id, items in by_mod.items():
        if mod_id not in mods_by_id:
            continue  # skip if mod ID doesn't exist in mods.json
        if len(items) == 1:
            best_per_mod[mod_id] = items[0]
        else:
            # Pick the item whose doc_name best matches the mod_name
            mod_name = mods_by_id[mod_id]['n'].lower()
            best = max(items, key=lambda x: difflib.SequenceMatcher(
                None, x['doc_name'].lower(), mod_name
            ).ratio())
            best_per_mod[mod_id] = best

    print(f"Unique mods to update: {len(best_per_mod)}")

    # ── Step 3: Build clean note text for each mod ──
    updates = []
    for mod_id, item in sorted(best_per_mod.items()):
        mod = mods_by_id[mod_id]
        existing = mod.get('no', '')
        existing_lower = existing.lower()

        # Build note parts from classified notes only
        parts = []
        for cn in item['classified_notes']:
            text = cn['text'].strip()
            note_type = cn['type']

            # Clean up the text
            text = re.sub(r'\s+', ' ', text)  # collapse whitespace
            # Remove URL/download references that leaked into note text
            text = re.sub(r'Download\s*\([^)]+\)', '', text).strip()
            text = re.sub(r'Forum\s*\([^)]+\)', '', text).strip()
            text = re.sub(r',\s*,', ',', text).strip().rstrip(',').strip()

            if not text or len(text) < 5:
                continue

            # Dedup: check if this info is already in existing notes
            text_lower = text.lower()

            if note_type == 'install_order':
                # Check if the key "before/after X" target is already mentioned
                m = re.search(r'(before|after)\s+(.+?)(?:\.|!|,|$)', text_lower)
                if m:
                    target = m.group(2).strip()[:20]
                    if target and target in existing_lower:
                        continue
                # Also skip if the sentence start already exists
                if text_lower[:30] in existing_lower:
                    continue

            elif note_type == 'npc_info':
                # Check if alignment code already present
                alignment_match = re.match(r'(LG|NG|CG|LN|TN|CN|LE|NE|CE)\b', text)
                if alignment_match and alignment_match.group(1).lower() in existing_lower:
                    continue

            elif note_type == 'warning':
                # Check rough word overlap
                key_words = set(re.findall(r'\w{5,}', text_lower))
                existing_words = set(re.findall(r'\w{5,}', existing_lower))
                if key_words and len(key_words & existing_words) / len(key_words) > 0.4:
                    continue

            elif note_type == 'component_rec':
                if text_lower[:25] in existing_lower:
                    continue

            # Truncate very long notes
            if len(text) > 200:
                # Try to find a clean break point
                break_pos = text.rfind('.', 0, 200)
                if break_pos > 50:
                    text = text[:break_pos + 1]
                else:
                    text = text[:200].rstrip() + '...'

            parts.append((note_type, text))

        if not parts:
            continue

        # Construct the new note
        new_text = ' '.join(t for _, t in parts)

        # Combine with existing
        if existing:
            combined = existing.rstrip() + ' ' + new_text
        else:
            combined = new_text

        updates.append({
            'mod_index': mod_id,
            'mod_name': mod['n'],
            'existing': existing,
            'addition': new_text,
            'combined': combined,
            'note_types': [nt for nt, _ in parts],
        })

    print(f"Mods with new content to add: {len(updates)}")

    # ── Step 4: Show summary and apply ──
    from collections import Counter
    type_counts = Counter()
    for u in updates:
        for nt in u['note_types']:
            type_counts[nt] += 1

    print(f"\nNote types being added:")
    for nt, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {nt:25s} {count:4d}")

    if dry_run:
        print(f"\n--- DRY RUN: showing first 25 updates ---")
        for u in updates[:25]:
            print(f"\n  i={u['mod_index']:4d} {u['mod_name'][:35]:35s}")
            print(f"    EXISTING: {(u['existing'] or '(none)')[:80]}")
            print(f"    ADD:      {u['addition'][:80]}")
        print(f"\n  ... {len(updates)} total updates")
        print("Re-run without --dry-run to apply.")
        return

    # Apply updates to mods list
    applied = 0
    for u in updates:
        for mod in mods:
            if mod['i'] == u['mod_index']:
                mod['no'] = u['combined']
                applied += 1
                break

    # Write back
    with open(mods_path, 'w', encoding='utf-8') as f:
        json.dump(mods, f, indent=2, ensure_ascii=False)

    print(f"\nApplied {applied} updates to {mods_path}")


if __name__ == '__main__':
    main()
