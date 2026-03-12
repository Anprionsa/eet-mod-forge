#!/usr/bin/env python3
"""
Extract conflict and dependency rules from EE-Mod-Setup Game.ini.

Parses the [Connections] section, matches tp2 names to mods.json,
resolves component IDs to display names, and outputs a review file.

Usage: python tools/extract_eemodsetup.py [--dry-run]
"""

import sys
import os
import json
import re
from collections import defaultdict, Counter

def parse_mod_refs(segment):
    """Parse a segment like 'modA(0|1)|modB(-)|modC(10&20)' into mod references.

    Returns list of (tp2_name, comp_ids) tuples.
    comp_ids is a list of strings: ['-'] for wildcard, ['0','1'] for specific.
    """
    refs = []
    # Split on | but not inside parentheses
    # Strategy: find each modName(compIDs) block
    for match in re.finditer(r'([A-Za-z0-9_#-]+)\(([^)]*)\)', segment):
        tp2 = match.group(1)
        comp_str = match.group(2)

        # Parse component IDs - split on | for alternatives
        # Ignore & (AND conditions) and ? (sub-choices) for now
        if comp_str == '-':
            comp_ids = ['-']
        else:
            # Split on | for alternatives, strip sub-choice suffixes (?1_1 etc)
            raw_parts = comp_str.split('|')
            comp_ids = []
            for part in raw_parts:
                # Handle AND conditions (a&b) by splitting
                for sub in part.split('&'):
                    # Strip sub-choice notation like ?1_1, ?1_2
                    clean = re.sub(r'\?.*', '', sub).strip()
                    if clean and clean != '-':
                        comp_ids.append(clean)
            if not comp_ids:
                comp_ids = ['-']

        refs.append((tp2, comp_ids))

    return refs


def parse_connections(text):
    """Parse the [Connections] section into structured rules."""
    start = text.find('[Connections]')
    if start < 0:
        return []

    # Find end of section
    section_text = text[start:]
    # Find next section header
    next_section = re.search(r'\n\[(?!Connections)', section_text[1:])
    if next_section:
        section_text = section_text[:next_section.start() + 1]

    rules = []
    for line in section_text.split('\n'):
        line = line.strip()
        if not line or line.startswith(';') or line.startswith('['):
            continue
        if '=' not in line:
            continue

        label, value = line.split('=', 1)
        label = label.strip()
        value = value.strip()

        # Determine rule type
        if value.startswith('C:'):
            rule_type = 'C'
            value = value[2:]
        elif value.startswith('CW:'):
            rule_type = 'CW'
            value = value[3:]
        elif value.startswith('D:'):
            rule_type = 'D'
            value = value[2:]
        else:
            continue

        # Split into sides by ':' but need to be careful -
        # colons separate sides: left:right or left:middle:right
        # But mod names can't contain colons, so split is safe
        sides = value.split(':')
        if len(sides) < 2:
            continue

        # Parse each side into mod references
        parsed_sides = []
        for side in sides:
            refs = parse_mod_refs(side)
            if refs:
                parsed_sides.append(refs)

        if len(parsed_sides) < 2:
            continue

        rules.append({
            'label': label,
            'type': rule_type,
            'sides': parsed_sides,
            'raw': line,
        })

    return rules


def expand_rules(rules):
    """Expand multi-side rules into pairwise entries."""
    expanded = []

    for rule in rules:
        rule_type = rule['type']
        sides = rule['sides']

        if rule_type in ('C', 'CW'):
            # Conflict: every mod on left side conflicts with every mod on right side
            # For 3+ sides, create pairwise between adjacent sides
            for i in range(len(sides) - 1):
                for ref_a in sides[i]:
                    for ref_b in sides[i + 1]:
                        tp2_a, comps_a = ref_a
                        tp2_b, comps_b = ref_b

                        # Skip self-conflicts
                        if tp2_a.lower() == tp2_b.lower():
                            expanded.append({
                                'type': rule_type,
                                'label': rule['label'],
                                'mod_a': tp2_a,
                                'mod_b': tp2_b,
                                'comps_a': comps_a,
                                'comps_b': comps_b,
                                'is_internal': True,
                            })
                            continue

                        expanded.append({
                            'type': rule_type,
                            'label': rule['label'],
                            'mod_a': tp2_a,
                            'mod_b': tp2_b,
                            'comps_a': comps_a,
                            'comps_b': comps_b,
                            'is_internal': False,
                        })

        elif rule_type == 'D':
            # Dependency: left side depends on right side
            # Usually: modA(comps) depends on modB(comps)
            if len(sides) >= 2:
                for ref_a in sides[0]:
                    for ref_b in sides[1]:
                        tp2_a, comps_a = ref_a
                        tp2_b, comps_b = ref_b

                        is_internal = tp2_a.lower() == tp2_b.lower()

                        expanded.append({
                            'type': 'D',
                            'label': rule['label'],
                            'mod_a': tp2_a,
                            'mod_b': tp2_b,
                            'comps_a': comps_a,
                            'comps_b': comps_b,
                            'is_internal': is_internal,
                        })

    return expanded


def resolve_comp_names(mod, comp_ids):
    """Resolve component IDs to display names using mod's co[] array."""
    if not mod.get('co') or comp_ids == ['-']:
        return None

    names = []
    for cid_str in comp_ids:
        try:
            cid = int(cid_str)
        except ValueError:
            continue

        # Find component with matching wc (WeiDU component ID)
        found = False
        for comp in mod['co']:
            if comp.get('wc') == cid:
                names.append(comp['n'])
                found = True
                break

        if not found:
            names.append(f'#{cid}')

    return ', '.join(names) if names else None


def main():
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    dry_run = '--dry-run' in sys.argv

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    mods_path = os.path.join(project_dir, 'data', 'mods.json')
    conflicts_path = os.path.join(project_dir, 'data', 'conflicts.json')
    cache_path = os.path.join(script_dir, 'game_ini_cache.txt')
    review_path = os.path.join(script_dir, 'eemodsetup_review.json')

    # Load mods.json
    with open(mods_path, 'r', encoding='utf-8') as f:
        mods = json.load(f)

    # Load conflicts.json
    with open(conflicts_path, 'r', encoding='utf-8') as f:
        existing = json.load(f)

    # Build tp2 lookup (case-insensitive)
    tp2_to_mod = {}
    for m in mods:
        tp2_to_mod[m['t'].lower()] = m

    print(f"Mods in database: {len(mods)}, unique tp2s: {len(tp2_to_mod)}")

    # Load Game.ini from cache
    if not os.path.exists(cache_path):
        print(f"ERROR: Cache file not found at {cache_path}")
        print("Run: python -c \"import urllib.request; open('tools/game_ini_cache.txt','w').write(urllib.request.urlopen('https://raw.githubusercontent.com/bujiasbitwise-contributions/EE-Mod-Setup/master/App/Config/EET/Game.ini').read().decode('utf-8'))\"")
        return

    with open(cache_path, 'r', encoding='utf-8') as f:
        ini_text = f.read()

    # ── Step 1: Parse rules ──
    raw_rules = parse_connections(ini_text)
    print(f"Raw rules parsed: {len(raw_rules)}")

    # ── Step 2: Expand to pairwise ──
    expanded = expand_rules(raw_rules)
    print(f"Expanded pairwise entries: {len(expanded)}")

    type_counts = Counter(e['type'] for e in expanded)
    internal = sum(1 for e in expanded if e['is_internal'])
    print(f"  C: {type_counts['C']}, CW: {type_counts['CW']}, D: {type_counts['D']}")
    print(f"  Internal (same-mod): {internal}, Cross-mod: {len(expanded) - internal}")

    # ── Step 3: Filter to cross-mod rules where both mods exist ──
    cross_mod = [e for e in expanded if not e['is_internal']]

    matched = []
    unmatched_tp2s = set()

    for entry in cross_mod:
        mod_a = tp2_to_mod.get(entry['mod_a'].lower())
        mod_b = tp2_to_mod.get(entry['mod_b'].lower())

        if not mod_a:
            unmatched_tp2s.add(entry['mod_a'])
        if not mod_b:
            unmatched_tp2s.add(entry['mod_b'])

        if mod_a and mod_b:
            # Resolve component names
            comp_a_names = resolve_comp_names(mod_a, entry['comps_a'])
            comp_b_names = resolve_comp_names(mod_b, entry['comps_b'])

            matched.append({
                'type': entry['type'],
                'label': entry['label'],
                'mod_a_tp2': mod_a['t'],
                'mod_b_tp2': mod_b['t'],
                'mod_a_id': mod_a['i'],
                'mod_b_id': mod_b['i'],
                'mod_a_name': mod_a['n'],
                'mod_b_name': mod_b['n'],
                'comps_a': entry['comps_a'],
                'comps_b': entry['comps_b'],
                'comp_a_display': comp_a_names,
                'comp_b_display': comp_b_names,
            })

    print(f"\nCross-mod matched (both mods in DB): {len(matched)}")
    print(f"Unmatched tp2 names: {len(unmatched_tp2s)}")
    if unmatched_tp2s:
        for tp2 in sorted(unmatched_tp2s)[:20]:
            print(f"  {tp2}")
        if len(unmatched_tp2s) > 20:
            print(f"  ... and {len(unmatched_tp2s) - 20} more")

    # ── Step 4: Deduplicate against existing conflicts ──
    # Build set of existing conflict pairs (normalized: sorted tp2 pair)
    existing_pairs = set()
    for c in existing.get('conflicts', []):
        pair = tuple(sorted([c['a'].lower(), c['b'].lower()]))
        existing_pairs.add(pair)

    existing_dep_pairs = set()
    for d in existing.get('dependencies', []):
        pair = (d['mod'].lower(), d['requires'].lower())
        existing_dep_pairs.add(pair)

    # Deduplicate matched rules
    new_conflicts = []
    new_deps = []
    dup_conflicts = 0
    dup_deps = 0

    # Track unique pairs to avoid adding the same pair multiple times
    seen_conflict_pairs = set()
    seen_dep_pairs = set()

    for entry in matched:
        a_tp2 = entry['mod_a_tp2']
        b_tp2 = entry['mod_b_tp2']

        if entry['type'] in ('C', 'CW'):
            pair = tuple(sorted([a_tp2.lower(), b_tp2.lower()]))

            if pair in existing_pairs:
                dup_conflicts += 1
                continue

            if pair in seen_conflict_pairs:
                # Already adding this pair - merge component info
                # Find existing entry and extend component info
                for existing_new in new_conflicts:
                    if tuple(sorted([existing_new['a'].lower(), existing_new['b'].lower()])) == pair:
                        # Merge component info if both have it
                        if entry['comp_a_display'] and existing_new.get('comp_a'):
                            if entry['comp_a_display'] not in existing_new['comp_a']:
                                existing_new['comp_a'] += '; ' + entry['comp_a_display']
                        elif entry['comp_a_display']:
                            existing_new['comp_a'] = entry['comp_a_display']

                        if entry['comp_b_display'] and existing_new.get('comp_b'):
                            if entry['comp_b_display'] not in existing_new['comp_b']:
                                existing_new['comp_b'] += '; ' + entry['comp_b_display']
                        elif entry['comp_b_display']:
                            existing_new['comp_b'] = entry['comp_b_display']
                        break
                continue

            seen_conflict_pairs.add(pair)

            severity = 'hard' if entry['type'] == 'C' else 'partial'
            conflict_entry = {
                'a': a_tp2,
                'b': b_tp2,
                'severity': severity,
                'reason': entry['label'],
                'source': 'eemodsetup',
            }

            if entry['comp_a_display']:
                conflict_entry['comp_a'] = entry['comp_a_display']
            if entry['comp_b_display']:
                conflict_entry['comp_b'] = entry['comp_b_display']

            new_conflicts.append(conflict_entry)

        elif entry['type'] == 'D':
            pair = (a_tp2.lower(), b_tp2.lower())

            if pair in existing_dep_pairs:
                dup_deps += 1
                continue

            if pair in seen_dep_pairs:
                continue

            seen_dep_pairs.add(pair)

            new_deps.append({
                'mod': a_tp2,
                'requires': b_tp2,
                'type': 'hard',
                'reason': entry['label'],
                'source': 'eemodsetup',
            })

    print(f"\n── Dedup results ──")
    print(f"Existing conflict pairs: {len(existing_pairs)}")
    print(f"Duplicate conflicts (already exist): {dup_conflicts}")
    print(f"New unique conflicts to add: {len(new_conflicts)}")
    print(f"  Hard: {sum(1 for c in new_conflicts if c['severity'] == 'hard')}")
    print(f"  Partial (warnings): {sum(1 for c in new_conflicts if c['severity'] == 'partial')}")
    print(f"Existing dep pairs: {len(existing_dep_pairs)}")
    print(f"Duplicate deps (already exist): {dup_deps}")
    print(f"New unique dependencies to add: {len(new_deps)}")

    # ── Step 5: Write review ──
    review = {
        'stats': {
            'raw_rules': len(raw_rules),
            'expanded': len(expanded),
            'internal': internal,
            'cross_mod_matched': len(matched),
            'unmatched_tp2s': len(unmatched_tp2s),
            'new_conflicts': len(new_conflicts),
            'new_deps': len(new_deps),
            'dup_conflicts': dup_conflicts,
            'dup_deps': dup_deps,
        },
        'unmatched_tp2s': sorted(unmatched_tp2s),
        'new_conflicts': new_conflicts,
        'new_deps': new_deps,
    }

    with open(review_path, 'w', encoding='utf-8') as f:
        json.dump(review, f, indent=2, ensure_ascii=False)

    print(f"\nReview written to {review_path}")

    # Show samples
    print(f"\n── Sample new conflicts (first 15) ──")
    for c in new_conflicts[:15]:
        comp_info = ''
        if c.get('comp_a') or c.get('comp_b'):
            comp_info = f" [{c.get('comp_a', '*')} vs {c.get('comp_b', '*')}]"
        print(f"  {c['severity']:7s} {c['a'][:25]:25s} <-> {c['b'][:25]:25s}{comp_info}")

    print(f"\n── Sample new dependencies (first 15) ──")
    for d in new_deps[:15]:
        print(f"  {d['mod'][:25]:25s} requires {d['requires'][:25]:25s} | {d['reason'][:60]}")


if __name__ == '__main__':
    main()
