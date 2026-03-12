#!/usr/bin/env python3
"""
Apply EE-Mod-Setup extracted rules to conflicts.json.

Reads tools/eemodsetup_review.json and merges new conflicts and
dependencies into data/conflicts.json. Also cleans up existing
entries that use display names instead of tp2 names.

Usage: python tools/apply_eemodsetup.py [--dry-run]
"""

import sys
import os
import json
import re


def build_name_to_tp2(mods):
    """Build display name → tp2 lookup for cleanup."""
    name_to_tp2 = {}
    for m in mods:
        name_to_tp2[m['n'].lower()] = m['t']
    return name_to_tp2


def is_tp2_name(name, tp2_set):
    """Check if a name matches a known tp2 name."""
    return name.lower() in tp2_set


def cleanup_identifier(name, tp2_set, name_to_tp2):
    """Try to resolve a display name to its tp2 name.
    Returns (resolved_name, was_changed)."""
    # Already a tp2 name
    if name.lower() in tp2_set:
        return name, False

    # Try exact display name match
    if name.lower() in name_to_tp2:
        return name_to_tp2[name.lower()], True

    # Try common patterns
    # "Spell Revisions" -> "spell_rev"
    # "Tweaks Anthology" -> "cdtweaks"
    # "SCS" -> "stratagems"
    manual_map = {
        'spell revisions': 'spell_rev',
        'tweaks anthology': 'cdtweaks',
        'scs': 'stratagems',
        'scs improved fiends': 'stratagems',
        'eet tweaks': 'EET_Tweaks',
        'house tweaks': 'HouseTweaks',
        'tweaks and tricks': 'tnt',
        'artisans kitpack': 'ArtisansKitpack',
        'might & guile': 'might_and_guile',
        'tome and blood': 'TomeAndBlood',
        'tome & blood': 'TomeAndBlood',
        'tome & blood familiars': 'TomeAndBlood',
        'refinements': 'rr',
        'enhanced powergaming scripts': 'EnhancedPowergamingScripts',
        'olvyn spells': 'MESpells',
        'shadow magic': 'shadowadept',
        'more style for mages': 'MSfM',
        'more style for mages': 'msfm',
        'skills and abilities': 'SkillsAndAbilitiesPfMW',
        'bgee leveled spawns': 'BG1EESpawn',
        'trap overhaul': 'CaedwyrTrapOverhaul',
        'trap overhaul - manually added': 'CaedwyrTrapOverhaul',
        'improved archer': 'improved_archer',
        'imoen forever': 'Imoen4Ever',
        'infinity sounds': 'A7-InfinitySounds',
        'npc ee': 'npc_ee',
        'celestials': 'celestials',
        'fnp sphere system': 'D5_FNP_SPHERE_SYSTEM',
        '5e spellcasting': '5ecasting',
        'another fine hell': 'C#AnotherFineHell',
        'improved shamanic dance': 'improvedshamanicdance',
        'transitions': 'transitions',
        'themed tweaks': 'themed_tweaks',
        's9 bgeenpc tweaks': 's9BGEENPCTweaks',
        'mih tweaks': 'mih_eq',
        'mih sp': 'mih_sp',
        'unfinished business bg1': 'bg1ub',
        'a7#golem construction': 'A7-GolemConstruction',
        'summonsfow': 'SummonsFoW',
        'klatu tweaks and tricks and tweaks': 'KLATU',
        'olvyn spells, klatu tweaks and tricks and tweaks': 'KLATU',
        'sr, iwdification, mih_sp': 'mih_sp',
        'tweaks and tricks and olvyn spells': 'tnt',
        'item pack': 'Item_Pack',
    }

    if name.lower() in manual_map:
        resolved = manual_map[name.lower()]
        if resolved.lower() in tp2_set:
            return resolved, True

    return name, False


def main():
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    dry_run = '--dry-run' in sys.argv

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    review_path = os.path.join(script_dir, 'eemodsetup_review.json')
    mods_path = os.path.join(project_dir, 'data', 'mods.json')
    conflicts_path = os.path.join(project_dir, 'data', 'conflicts.json')

    with open(review_path, 'r', encoding='utf-8') as f:
        review = json.load(f)
    with open(mods_path, 'r', encoding='utf-8') as f:
        mods = json.load(f)
    with open(conflicts_path, 'r', encoding='utf-8') as f:
        conflicts = json.load(f)

    tp2_set = {m['t'].lower() for m in mods}
    name_to_tp2 = build_name_to_tp2(mods)

    # ── Step 1: Clean up existing entries ──
    cleanup_count = 0
    for c in conflicts.get('conflicts', []):
        a_new, a_changed = cleanup_identifier(c['a'], tp2_set, name_to_tp2)
        b_new, b_changed = cleanup_identifier(c['b'], tp2_set, name_to_tp2)
        if a_changed:
            if dry_run:
                print(f"  CLEANUP conflict.a: '{c['a']}' -> '{a_new}'")
            c['a'] = a_new
            cleanup_count += 1
        if b_changed:
            if dry_run:
                print(f"  CLEANUP conflict.b: '{c['b']}' -> '{b_new}'")
            c['b'] = b_new
            cleanup_count += 1

    for d in conflicts.get('dependencies', []):
        m_new, m_changed = cleanup_identifier(d['mod'], tp2_set, name_to_tp2)
        r_new, r_changed = cleanup_identifier(d['requires'], tp2_set, name_to_tp2)
        if m_changed:
            if dry_run:
                print(f"  CLEANUP dep.mod: '{d['mod']}' -> '{m_new}'")
            d['mod'] = m_new
            cleanup_count += 1
        if r_changed:
            if dry_run:
                print(f"  CLEANUP dep.requires: '{d['requires']}' -> '{r_new}'")
            d['requires'] = r_new
            cleanup_count += 1

    print(f"Identifiers cleaned up: {cleanup_count}")

    # ── Step 2: Append new conflicts ──
    new_conflicts = review['new_conflicts']
    new_deps = review['new_deps']

    print(f"New conflicts to add: {len(new_conflicts)}")
    print(f"New dependencies to add: {len(new_deps)}")

    if dry_run:
        print(f"\n--- DRY RUN: showing first 20 new conflicts ---")
        for c in new_conflicts[:20]:
            comp_info = ''
            if c.get('comp_a') or c.get('comp_b'):
                comp_info = f" [{c.get('comp_a', '*')[:30]} vs {c.get('comp_b', '*')[:30]}]"
            print(f"  {c['severity']:7s} {c['a'][:25]:25s} <-> {c['b'][:25]:25s}{comp_info}")

        print(f"\n--- DRY RUN: showing first 20 new deps ---")
        for d in new_deps[:20]:
            print(f"  {d['mod'][:25]:25s} requires {d['requires'][:25]:25s}")

        print(f"\nTotal conflicts after merge: {len(conflicts.get('conflicts', [])) + len(new_conflicts)}")
        print(f"Total deps after merge: {len(conflicts.get('dependencies', [])) + len(new_deps)}")
        print("Re-run without --dry-run to apply.")
        return

    # Append
    conflicts['conflicts'].extend(new_conflicts)
    conflicts['dependencies'].extend(new_deps)

    # Write back
    with open(conflicts_path, 'w', encoding='utf-8') as f:
        json.dump(conflicts, f, indent=2, ensure_ascii=False)

    total_c = len(conflicts['conflicts'])
    total_d = len(conflicts['dependencies'])
    print(f"\nApplied to {conflicts_path}")
    print(f"Total conflicts: {total_c}")
    print(f"Total dependencies: {total_d}")


if __name__ == '__main__':
    main()
