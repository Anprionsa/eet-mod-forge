#!/usr/bin/env python3
"""
Extract mod notes from the Infinity Insanity docx for enriching mods.json.

Parses the install order section (paragraphs 301-1583), matches entries to
mods in mods.json via GitHub repo names and display name fuzzy matching,
classifies note types, and outputs a review JSON file.

Usage: python tools/extract_ii_notes.py <path_to_docx>
Output: tools/ii_review.json
"""

import sys
import os
import re
import json
import zipfile
import difflib
import xml.etree.ElementTree as ET
from collections import Counter

# ── XML Namespaces ──────────────────────────────────────────────────────────

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
R_EMBED = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
REL_NS = '{http://schemas.openxmlformats.org/package/2006/relationships}'

# ── 1. DOCX Parsing ────────────────────────────────────────────────────────

def load_docx(docx_path):
    """Extract document.xml and hyperlink relationships from docx."""
    with zipfile.ZipFile(docx_path, 'r') as z:
        doc_xml = z.read('word/document.xml')
        rels_xml = z.read('word/_rels/document.xml.rels')

    doc_root = ET.fromstring(doc_xml)
    rels_root = ET.fromstring(rels_xml)

    # Build relationship ID -> URL mapping (external hyperlinks only)
    rels = {}
    for rel in rels_root.findall(f'{REL_NS}Relationship'):
        if rel.get('TargetMode') == 'External':
            rels[rel.get('Id')] = rel.get('Target', '')

    return doc_root, rels


def get_paragraphs(doc_root):
    """Get all paragraph elements from document body."""
    body = doc_root.find(f'{W}body')
    return body.findall(f'{W}p')


def get_paragraph_style(para):
    """Get paragraph style name (e.g., 'Heading1', 'Heading3')."""
    ppr = para.find(f'{W}pPr')
    if ppr is not None:
        ps = ppr.find(f'{W}pStyle')
        if ps is not None:
            return ps.get(f'{W}val', '')
    return ''


def extract_text_and_links(para, rels):
    """Extract full text and hyperlink URLs from a paragraph."""
    texts = []
    links = []

    for child in para:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag

        if tag == 'r':
            # Regular run
            for t in child.findall(f'{W}t'):
                if t.text:
                    texts.append(t.text)

        elif tag == 'hyperlink':
            # Hyperlink - extract URL and visible text
            rid = child.get(f'{R}id', '')
            url = rels.get(rid, '')
            link_text_parts = []
            for r in child.findall(f'{W}r'):
                for t in r.findall(f'{W}t'):
                    if t.text:
                        link_text_parts.append(t.text)
            link_text = ''.join(link_text_parts)
            texts.append(link_text)
            if url:
                links.append({'url': url, 'text': link_text})

    return ''.join(texts).strip(), links


# ── 2. GitHub Repo Extraction ──────────────────────────────────────────────

GITHUB_RE = re.compile(r'github\.com/([^/]+)/([^/?\#]+)', re.I)

def extract_repo_from_url(url):
    """Extract (owner, repo_name) from a GitHub URL, or None."""
    m = GITHUB_RE.search(url)
    if not m:
        return None
    owner = m.group(1)
    repo = m.group(2)
    # Strip common suffixes
    for suffix in ['/releases', '/release', '/tree', '/archive', '/blob',
                   '/master', '/main', '.git']:
        if repo.lower().endswith(suffix.lstrip('/')):
            repo = repo[:len(repo) - len(suffix.lstrip('/'))]
    return (owner.lower(), repo.lower().rstrip('/'))


# ── 3. Mod Entry Detection ─────────────────────────────────────────────────

def is_mod_entry(text, links):
    """Detect if a paragraph is a mod entry (name: Download...)."""
    if not text or len(text) < 20:
        return False
    # Must have a colon within first 120 chars
    colon_pos = text.find(':')
    if colon_pos < 3 or colon_pos > 120:
        return False
    # Must have at least one link (Download or Forum)
    if not links:
        return False
    # Check that at least one link text mentions Download or Forum
    for link in links:
        lt = link['text'].lower()
        if any(kw in lt for kw in ['download', 'forum', 'github', 'thread']):
            return True
    return False


def parse_mod_name(text):
    """Extract mod display name from the beginning of entry text."""
    colon_pos = text.find(':')
    if colon_pos < 0:
        return text[:80]
    name = text[:colon_pos].strip()
    # Strip "for BG1", "for BG2", etc.
    name = re.sub(r'\s+for\s+(BG[12]|BGEE|BG2EE|BG:?EE|EET|SoA|SoD|ToB).*$', '', name, flags=re.I)
    return name.strip()


def parse_body_text(text):
    """Extract the body/description text after the mod name."""
    colon_pos = text.find(':')
    if colon_pos < 0:
        return text
    return text[colon_pos + 1:].strip()


# ── 4. Note Classification ─────────────────────────────────────────────────

INSTALL_ORDER_RE = re.compile(
    r'[Ii]nstall\s+.*?\s+(before|after|prior\s+to)\s+',
    re.I
)
INSTALL_ORDER_RE2 = re.compile(
    r'(?:must|should)\s+(?:be\s+)?install(?:ed)?\s+(?:before|after|prior)',
    re.I
)

WARNING_RE = re.compile(r'WARNING[:\!]|CAUTION[:\!]', re.I)
WARNING_SOFT_RE = re.compile(
    r'\b(?:buggy|broken|crash(?:es|ing)?|incompatible\s+with|known\s+(?:bug|issue)|may\s+(?:not\s+work|cause\s+trouble))\b',
    re.I
)

NPC_RE = re.compile(
    r'\b(LG|NG|CG|LN|TN|CN|LE|NE|CE)\s+(Male|Female)\s+'
    r'(Human|Elf|Half-Elf|Halfling|Gnome|Dwarf|Tiefling|Aasimar|Half-Orc|Drow|Rakshasa|'
    r'Human/Dragon|Half-Dragon|Vampire|Roc)\s+'
    r'(Fighter|Mage|Cleric|Thief|Ranger|Paladin|Bard|Druid|Sorcerer|Monk|Shaman|Barbarian|'
    r'Fighter/Thief|Fighter/Mage|Cleric/Mage|Fighter/Wizard|Cleric/Thief|Illusionist/Thief|'
    r'Wizard\s+Slayer|Berserker|Kensai|Assassin|Swashbuckler|Bounty\s+Hunter|Archer|Stalker|'
    r'Avenger|Shapeshifter|Totemic\s+Druid|Beast\s+Master|Jester|Blade|Skald|Enchanter|Invoker|'
    r'Necromancer|Conjurer|Diviner|Transmuter|Wild\s+Mage)',
    re.I
)

COMPONENT_REC_RE = re.compile(
    r"(?:install\s+(?:only|here\s+and\s+now\s+only)|don['\u2019]t\s+install\s+(?:the\s+)?component|"
    r"skip\s+(?:the\s+)?component|use\s+(?:only\s+)?(?:the\s+)?component|"
    r"recommended\s*:?\s*component|install\s+option\s+\d|"
    r"we['\u2019]re\s+using\s+(?:the\s+)?(?:below|following)\s+(?:options|components)|"
    r"use\s+the\s+(?:below|following)\s+components)",
    re.I
)


def classify_body(body_text):
    """Classify body text into note types. Returns list of (type, text) tuples."""
    notes = []

    # Split into sentences for classification
    sentences = re.split(r'(?<=[.!?])\s+', body_text)

    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 5:
            continue

        # Install order directives
        if INSTALL_ORDER_RE.search(sent) or INSTALL_ORDER_RE2.search(sent):
            # Extract just the directive part
            notes.append(('install_order', sent))
            continue

        # Warnings
        if WARNING_RE.search(sent) or WARNING_SOFT_RE.search(sent):
            notes.append(('warning', sent))
            continue

        # NPC info
        m = NPC_RE.search(sent)
        if m:
            notes.append(('npc_info', m.group(0).strip()))
            continue

        # Component recommendations
        if COMPONENT_REC_RE.search(sent):
            notes.append(('component_rec', sent))
            continue

    return notes


def build_proposed_note(classified_notes, existing_notes):
    """Build a proposed note string from classified notes, deduping against existing."""
    existing_lower = (existing_notes or '').lower()
    new_parts = []

    for note_type, text in classified_notes:
        # Clean up the text
        text = text.strip()
        if not text:
            continue
        # Check if substance is already in existing notes
        # Use a simplified check - lowercase key phrases
        text_lower = text.lower()
        # For install order, check if the target mod name is already mentioned
        if note_type == 'install_order':
            # Extract the "before/after X" part
            m = re.search(r'(before|after)\s+(.+?)(?:\.|!|$)', text_lower)
            if m and m.group(2).strip() in existing_lower:
                continue
        elif note_type == 'npc_info':
            # Check if alignment code is already present
            m = NPC_RE.search(text)
            if m and m.group(1).lower() in existing_lower:
                continue
        elif note_type == 'warning':
            # Check rough overlap
            key_words = set(re.findall(r'\w{5,}', text_lower))
            existing_words = set(re.findall(r'\w{5,}', existing_lower))
            if len(key_words & existing_words) > len(key_words) * 0.5:
                continue
        else:
            # Generic dedup
            if text_lower[:30] in existing_lower:
                continue

        new_parts.append((note_type, text))

    return new_parts


# ── 5. Matching Engine ──────────────────────────────────────────────────────

def build_mod_index(mods_path, github_mods_path):
    """Build lookup indexes from mods.json and github_mods.json."""
    with open(mods_path, 'r', encoding='utf-8') as f:
        mods = json.load(f)
    with open(github_mods_path, 'r', encoding='utf-8') as f:
        github_mods = json.load(f)

    # Index by mod i
    by_id = {m['i']: m for m in mods}

    # Index by github repo name (from github_mods.json)
    by_repo = {}
    for gm in github_mods:
        repo_lower = gm['r'].lower()
        owner_lower = gm['o'].lower()
        by_repo[repo_lower] = gm['i']
        by_repo[f"{owner_lower}/{repo_lower}"] = gm['i']

    # Also extract repos from mods.json u field for mods not in github_mods
    github_ids = {gm['i'] for gm in github_mods}
    for m in mods:
        if m['i'] not in github_ids and 'u' in m:
            repo_info = extract_repo_from_url(m['u'])
            if repo_info:
                owner, repo = repo_info
                by_repo[repo] = m['i']
                by_repo[f"{owner}/{repo}"] = m['i']

    # Index by normalized display name
    by_name = {}
    for m in mods:
        norm = normalize_name(m['n'])
        if norm not in by_name:
            by_name[norm] = []
        by_name[norm].append(m['i'])

    return by_id, by_repo, by_name, mods


def normalize_name(name):
    """Normalize a mod name for fuzzy matching."""
    n = name.lower()
    # Strip common suffixes
    n = re.sub(r'\s+for\s+(bg[12]|bgee|bg2ee|eet|soa|sod|tob).*$', '', n)
    n = re.sub(r'\s+aka\s+.*$', '', n)
    n = re.sub(r'\s+npc$', '', n)
    n = re.sub(r'\s+mod$', '', n)
    n = re.sub(r'\(.*?\)', '', n)
    n = re.sub(r'[^a-z0-9\s-]', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def match_entry(doc_entry, by_repo, by_name, by_id):
    """Match a doc entry to a mod in mods.json. Returns (mod_index, method, confidence)."""
    # 1. Try GitHub repo match (highest confidence)
    for link in doc_entry['links']:
        repo_info = extract_repo_from_url(link['url'])
        if repo_info:
            owner, repo = repo_info
            # Try full owner/repo first
            full_key = f"{owner}/{repo}"
            if full_key in by_repo:
                return by_repo[full_key], 'repo_exact', 1.0
            # Try repo name only
            if repo in by_repo:
                return by_repo[repo], 'repo_name', 0.95

    # 2. Try normalized name exact match
    doc_norm = normalize_name(doc_entry['display_name'])
    if doc_norm in by_name:
        candidates = by_name[doc_norm]
        if len(candidates) == 1:
            return candidates[0], 'name_exact', 0.90
        # Multiple matches - return first (could improve with category context)
        return candidates[0], 'name_exact_multi', 0.75

    # 3. Fuzzy name match
    best_ratio = 0
    best_id = None
    for norm_name, ids in by_name.items():
        ratio = difflib.SequenceMatcher(None, doc_norm, norm_name).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_id = ids[0]

    if best_ratio >= 0.80:
        return best_id, 'name_fuzzy', round(best_ratio, 2)
    elif best_ratio >= 0.65:
        return best_id, 'name_fuzzy_low', round(best_ratio, 2)

    return None, 'unmatched', 0.0


# ── 6. Main Pipeline ───────────────────────────────────────────────────────

def main():
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    if len(sys.argv) < 2:
        print("Usage: python tools/extract_ii_notes.py <path_to_docx>")
        sys.exit(1)

    docx_path = sys.argv[1]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    mods_path = os.path.join(project_dir, 'data', 'mods.json')
    github_mods_path = os.path.join(project_dir, 'data', 'github_mods.json')
    output_path = os.path.join(script_dir, 'ii_review.json')

    print(f"Loading docx: {docx_path}")
    doc_root, rels = load_docx(docx_path)
    paragraphs = get_paragraphs(doc_root)
    print(f"Total paragraphs: {len(paragraphs)}")

    print(f"Loading mods database...")
    by_id, by_repo, by_name, all_mods = build_mod_index(mods_path, github_mods_path)
    print(f"Loaded {len(all_mods)} mods, {len(by_repo)} repo keys, {len(by_name)} name keys")

    # ── Extract install order entries (paragraphs 301-1583) ──
    START_PARA = 301
    END_PARA = min(1584, len(paragraphs))
    current_category = "UNKNOWN"
    entries = []
    stats = Counter()

    print(f"\nScanning paragraphs {START_PARA}-{END_PARA}...")

    for idx in range(START_PARA, END_PARA):
        para = paragraphs[idx]
        style = get_paragraph_style(para)
        text, links = extract_text_and_links(para, rels)

        if not text:
            continue

        # Track category headings
        if style.startswith('Heading'):
            # Extract category name from heading text
            # e.g., "[1.9.4] #4: Post-EET Start:Early & Overwriting Mods"
            m = re.match(r'\[[\d.]+\]\s*#?\d*:?\s*(.*)', text)
            if m:
                current_category = m.group(1).strip()
            continue

        # Detect mod entries
        if is_mod_entry(text, links):
            display_name = parse_mod_name(text)
            body_text = parse_body_text(text)
            entries.append({
                'display_name': display_name,
                'body_text': body_text,
                'full_text': text,
                'links': links,
                'paragraph_index': idx,
                'category': current_category,
            })
            stats['entries'] += 1
        else:
            # Check if it's a standalone install directive
            if entries and INSTALL_ORDER_RE.search(text):
                # Append to the last entry's body
                entries[-1]['body_text'] += ' ' + text
                stats['appended_directives'] += 1

    print(f"Extracted {stats['entries']} mod entries, {stats['appended_directives']} appended directives")

    # ── Match and classify ──
    review_items = []
    match_stats = Counter()
    note_stats = Counter()

    for entry in entries:
        mod_id, method, confidence = match_entry(entry, by_repo, by_name, by_id)
        match_stats[method] += 1

        if mod_id is None:
            review_items.append({
                'mod_index': None,
                'mod_name': entry['display_name'],
                'doc_name': entry['display_name'],
                'match_method': method,
                'match_confidence': confidence,
                'current_notes': None,
                'classified_notes': [],
                'proposed_addition': '',
                'source_paragraph': entry['paragraph_index'],
                'source_category': entry['category'],
                'action': 'unmatched',
            })
            continue

        mod = by_id.get(mod_id, {})
        existing_notes = mod.get('no', '')
        classified = classify_body(entry['body_text'])
        new_notes = build_proposed_note(classified, existing_notes)

        for nt, _ in new_notes:
            note_stats[nt] += 1

        # Determine action
        if not new_notes:
            action = 'skip'
        elif not existing_notes:
            action = 'add'
        else:
            action = 'merge'

        # Build proposed addition text
        proposed_parts = []
        for nt, text in new_notes:
            proposed_parts.append(text)
        proposed = ' '.join(proposed_parts)

        review_items.append({
            'mod_index': mod_id,
            'mod_name': mod.get('n', ''),
            'doc_name': entry['display_name'],
            'match_method': method,
            'match_confidence': confidence,
            'current_notes': existing_notes or None,
            'classified_notes': [{'type': nt, 'text': t} for nt, t in new_notes],
            'proposed_addition': proposed,
            'source_paragraph': entry['paragraph_index'],
            'source_category': entry['category'],
            'action': action,
        })

    # ── Write review file ──
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(review_items, f, indent=2, ensure_ascii=False)

    # ── Print statistics ──
    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE")
    print(f"{'='*60}")
    print(f"\nTotal doc entries:  {len(entries)}")
    print(f"Review items:       {len(review_items)}")
    print(f"\nMatch Results:")
    for method, count in sorted(match_stats.items(), key=lambda x: -x[1]):
        print(f"  {method:25s} {count:4d}")
    print(f"\nNote Types Found:")
    for nt, count in sorted(note_stats.items(), key=lambda x: -x[1]):
        print(f"  {nt:25s} {count:4d}")
    print(f"\nActions:")
    action_counts = Counter(item['action'] for item in review_items)
    for action, count in sorted(action_counts.items(), key=lambda x: -x[1]):
        print(f"  {action:25s} {count:4d}")
    print(f"\nOutput: {output_path}")

    # Print unmatched entries for investigation
    unmatched = [item for item in review_items if item['action'] == 'unmatched']
    if unmatched:
        print(f"\n{'='*60}")
        print(f"UNMATCHED ENTRIES ({len(unmatched)}):")
        print(f"{'='*60}")
        for item in unmatched:
            print(f"  P{item['source_paragraph']:4d} | {item['doc_name'][:60]}")


if __name__ == '__main__':
    main()
