#!/usr/bin/env python3
"""
EET Mod Forge - Complete Data Pipeline v3
Fixes: mod-level notes, installed matching, CSV matching, PI→WeiDU mapping
Outputs: app-ready JSON with accurate WeiDU.log generation data
"""

import re, json, csv
from collections import defaultdict, Counter

# ═══════════════════════════════════════════════════════════════
# 1. Parse WeiDU logs
# ═══════════════════════════════════════════════════════════════

def parse_weidu_logs():
    """Parse both WeiDU logs into structured entries."""
    all_entries = []
    by_folder = defaultdict(list)
    
    for logfile, is_bgee in [('/mnt/project/WeiDU.log', False), ('/mnt/project/WeiDU-BGEE.log', True)]:
        with open(logfile, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('//'):
                    continue
                m = re.match(
                    r'~([^\\]+)\\([^~]+)~\s+#(\d+)\s+#(\d+)\s+//\s*(?:\[([^\]]*)\]\s*(?:->\s*)?)?(.+?)(?::\s+(.+))?$',
                    line
                )
                if m:
                    entry = {
                        'folder': m.group(1),
                        'tp2_file': m.group(2),
                        'tp2_path': f"{m.group(1)}\\{m.group(2)}",
                        'lang': int(m.group(3)),
                        'comp': int(m.group(4)),
                        'subcomp': (m.group(5) or '').strip(),
                        'name': m.group(6).strip(),
                        'version': (m.group(7) or '').strip(),
                        'is_bgee': is_bgee,
                        'raw_line': line,
                    }
                    all_entries.append(entry)
                    by_folder[entry['folder'].lower()].append(entry)
    
    return all_entries, by_folder


# ═══════════════════════════════════════════════════════════════
# 2. Parse install order text file
# ═══════════════════════════════════════════════════════════════

L1_SECTIONS = {s.upper() for s in [
    "PRE EET BGEE MODS", "EET STARTS HERE", "ENGINE", "INTERFACE",
    "GRAPHICAL AND SOUND OVERWRITE MODS", "RESTORATIONS",
    "QUEST MODS BG1", "QUEST MODS BG2", "QUEST MODS ToB",
    "NEW NPC MODS", "AFTER NEW NPCS", "CREATURE MODS PRE SCS",
    "EXPERIENCE TWEAKS", "ITEM ADDITION MODS", "SPELL MODS",
    "KIT MODS", "POST SCS TWEAKS",
]}

def parse_install_order():
    """Parse the install order text with proper note attachment."""
    with open('/mnt/project/777087788-install-EET-4.txt', 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    
    COLON_RE = re.compile(r'^(\s*//)?\s*([A-Za-z][A-Za-z0-9_#-]*):(\d+);(.+)$')
    PI_RE = re.compile(r'^(\s*//)?\s*([A-Za-z][A-Za-z0-9_#-]+);(.+)$')
    URL_RE = re.compile(r'(https?://[^\s<>"\']+)')
    
    mods = []  # Final mod list
    current_cat = ""
    current_sub = ""
    pending_url = None
    pending_notes = []
    current_mod = None
    current_mod_notes = []
    order_pos = 0
    
    def get_mod_key(tp2_base=None, pi_label=None, desc=""):
        """Get a grouping key for mod entries."""
        if tp2_base:
            return tp2_base.lower()
        # For PI labels, group by mod name from description
        parts = desc.split(' - ', 1)
        return parts[0].strip().lower() if parts else pi_label.lower()
    
    def flush_mod():
        nonlocal current_mod, current_mod_notes
        if current_mod:
            if current_mod_notes:
                existing = current_mod.get('notes', '')
                new_notes = '\n'.join(current_mod_notes)
                current_mod['notes'] = f"{existing}\n{new_notes}".strip() if existing else new_notes
            mods.append(current_mod)
        current_mod = None
        current_mod_notes = []
    
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        i += 1
        stripped = line.strip()
        
        if not stripped:
            continue
        
        # Section headers
        if stripped.startswith('///'):
            header = stripped.strip('/').strip()
            if not header or 'Advanced users only' in header or "aren't even" in header:
                continue
            if re.match(r'^/{8,}$', stripped):
                continue
            if header.upper() in L1_SECTIONS:
                flush_mod()
                current_cat = header
                current_sub = ""
            else:
                flush_mod()
                current_sub = header
            continue
        
        # Decorative dividers
        if re.match(r'^/{8,}\s*$', stripped):
            continue
        
        # Try colon format
        cm = COLON_RE.match(stripped)
        if cm:
            is_commented = bool(cm.group(1) and cm.group(1).strip())
            tp2_base = cm.group(2)
            comp_num = int(cm.group(3))
            desc = cm.group(4).strip()
            
            # Multi-line continuation
            while i < len(lines):
                nxt = lines[i].rstrip().strip()
                if not nxt or nxt.startswith('//') or COLON_RE.match(nxt) or PI_RE.match(nxt) or nxt.startswith('///'):
                    break
                desc += ' ' + nxt
                i += 1
            
            desc_parts = desc.split(' - ', 1)
            mod_name = desc_parts[0].strip()
            comp_name = desc_parts[1].strip() if len(desc_parts) > 1 else desc
            
            mod_key = tp2_base.lower()
            
            component = {
                'format': 'colon',
                'tp2_base': tp2_base,
                'comp_num': comp_num,
                'pi_label': None,
                'map_key': f"{tp2_base}:{comp_num}",
                'name': comp_name,
                'full_desc': desc,
                'commented': is_commented,
            }
            
            if current_mod and current_mod['_key'] == mod_key:
                # Appending to existing mod — notes go to component
                if pending_notes:
                    component['notes'] = '\n'.join(pending_notes)
                    pending_notes = []
                current_mod['components'].append(component)
            else:
                # New mod — pending notes go to the mod, not component
                flush_mod()
                order_pos += 1
                mod_notes = '\n'.join(pending_notes) if pending_notes else ''
                pending_notes = []
                current_mod = {
                    '_key': mod_key,
                    'id': order_pos,
                    'tp2_base': tp2_base,
                    'mod_name': mod_name,
                    'category': current_cat,
                    'subcategory': current_sub,
                    'url': pending_url,
                    'notes': mod_notes,
                    'components': [component],
                }
                current_mod_notes = []
                pending_url = None
            continue
        
        # Try PI format
        pm = PI_RE.match(stripped)
        if pm:
            is_commented = bool(pm.group(1) and pm.group(1).strip())
            pi_label = pm.group(2)
            desc = pm.group(3).strip()
            
            while i < len(lines):
                nxt = lines[i].rstrip().strip()
                if not nxt or nxt.startswith('//') or COLON_RE.match(nxt) or PI_RE.match(nxt) or nxt.startswith('///'):
                    break
                desc += ' ' + nxt
                i += 1
            
            desc_parts = desc.split(' - ', 1)
            mod_name = desc_parts[0].strip()
            comp_name = desc_parts[1].strip() if len(desc_parts) > 1 else desc
            
            mod_key = mod_name.lower()
            
            component = {
                'format': 'pi',
                'tp2_base': None,
                'comp_num': None,
                'pi_label': pi_label,
                'map_key': pi_label,
                'name': comp_name,
                'full_desc': desc,
                'commented': is_commented,
            }
            
            if current_mod and current_mod['_key'] == mod_key:
                if pending_notes:
                    component['notes'] = '\n'.join(pending_notes)
                    pending_notes = []
                current_mod['components'].append(component)
            else:
                flush_mod()
                order_pos += 1
                mod_notes = '\n'.join(pending_notes) if pending_notes else ''
                pending_notes = []
                current_mod = {
                    '_key': mod_key,
                    'id': order_pos,
                    'tp2_base': pi_label.split('-')[0] if '-' in pi_label else pi_label,
                    'mod_name': mod_name,
                    'category': current_cat,
                    'subcategory': current_sub,
                    'url': pending_url,
                    'notes': mod_notes,
                    'components': [component],
                }
                current_mod_notes = []
                pending_url = None
            continue
        
        # Comment lines
        if stripped.startswith('//'):
            content = stripped.lstrip('/').strip()
            urls = URL_RE.findall(content)
            if urls:
                pending_url = urls[0]
                remaining = content
                for u in urls:
                    remaining = remaining.replace(u, '').strip()
                if remaining:
                    pending_notes.append(remaining)
            elif content:
                # If we're between mods (no current_mod), these are pending notes
                # for the next mod. If inside a mod, they're inter-component notes.
                pending_notes.append(content)
            continue
        
        # Non-entry, non-comment continuation
        if stripped:
            pending_notes.append(stripped)
    
    flush_mod()
    
    # Filter noise
    mods = [m for m in mods if m['mod_name'] and len(m['mod_name']) < 200 
            and m['_key'] not in ('being', 'group', 'items', 'defense', 'automatically')]
    
    # Clean up internal key
    for m in mods:
        del m['_key']
    
    return mods


# ═══════════════════════════════════════════════════════════════
# 3. Parse CSV metadata with strict matching
# ═══════════════════════════════════════════════════════════════

def parse_csv_metadata():
    """Parse CSV with strict deduped index."""
    mods = {}
    with open('/mnt/project/EET_Mod_Install_Order_Guide__EET.csv', 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get('Mod Name') or '').strip()
            if not name:
                continue
            tp2 = (row.get('.tp2') or '').strip()
            
            entry = {
                'name': name, 'tp2': tp2,
                'category': (row.get('Category') or '').strip(),
                'description': (row.get('Description') or '').strip(),
                'authors': (row.get('Authors & Maintainers') or '').strip(),
                'homepage': (row.get('Homepage') or '').strip(),
                'github': (row.get('GitHub/DL') or '').strip(),
                'readme': (row.get('Readme') or '').strip(),
                'forum': (row.get('Forum') or '').strip(),
                'requires': (row.get('Requires') or '').strip(),
                'incompatibilities': (row.get('Incompatibilities') or '').strip(),
                'bugs': (row.get('Bugs') or '').strip(),
                'game_phases': {
                    'bg1': bool((row.get('BG') or '').strip()),
                    'sod': bool((row.get('SoD') or '').strip()),
                    'soa': bool((row.get('SoA') or '').strip()),
                    'tob': bool((row.get('ToB') or '').strip()),
                },
            }
            # Index by exact tp2 and exact name (no fuzzy)
            if tp2:
                mods[tp2.lower()] = entry
            mods[name.lower()] = entry
    
    return mods


# ═══════════════════════════════════════════════════════════════
# 4. Merge everything
# ═══════════════════════════════════════════════════════════════

def merge_all():
    print("1. Parsing WeiDU logs...")
    weidu_entries, weidu_by_folder = parse_weidu_logs()
    print(f"   {len(weidu_entries)} entries, {len(weidu_by_folder)} folders")
    
    print("2. Parsing install order...")
    mods = parse_install_order()
    total_comps = sum(len(m['components']) for m in mods)
    print(f"   {len(mods)} mods, {total_comps} components")
    
    print("3. Parsing CSV metadata...")
    csv_mods = parse_csv_metadata()
    print(f"   {len(csv_mods)} entries")
    
    print("4. Loading PI→WeiDU mapping...")
    with open('pi_weidu_map.json') as f:
        pi_map = json.load(f)
    print(f"   {len(pi_map)} mappings")
    
    # Build installed lookup
    installed = {}
    for we in weidu_entries:
        key = f"{we['folder'].lower()}:{we['comp']}"
        installed[key] = we
    
    print("5. Enriching mods...")
    
    # Stats
    csv_matched = 0
    inst_matched = 0
    
    for mod in mods:
        tp2_lower = mod['tp2_base'].lower()
        name_lower = mod['mod_name'].lower()
        
        # CSV enrichment (strict first, then safe fuzzy)
        csv_match = csv_mods.get(tp2_lower) or csv_mods.get(name_lower)
        if not csv_match:
            # Safe fuzzy: normalize and try
            import unicodedata
            def norm(s):
                return re.sub(r'[^a-z0-9]', '', s.lower())
            tp2_norm = norm(tp2_lower)
            name_norm = norm(name_lower)
            for ck, cv in csv_mods.items():
                ck_norm = norm(ck)
                if len(tp2_norm) >= 5 and (tp2_norm == ck_norm or 
                    (len(tp2_norm) >= 8 and tp2_norm in ck_norm) or
                    (len(ck_norm) >= 8 and ck_norm in tp2_norm)):
                    csv_match = cv
                    break
                if len(name_norm) >= 5 and (name_norm == ck_norm or
                    (len(name_norm) >= 8 and name_norm in ck_norm) or
                    (len(ck_norm) >= 8 and ck_norm in name_norm)):
                    csv_match = cv
                    break
        if csv_match:
            mod['authors'] = csv_match.get('authors', '')
            mod['homepage'] = csv_match.get('homepage', '')
            mod['github'] = csv_match.get('github', '')
            mod['forum'] = csv_match.get('forum', '')
            mod['csv_desc'] = csv_match.get('description', '')
            mod['requires'] = csv_match.get('requires', '')
            mod['incompatibilities'] = csv_match.get('incompatibilities', '')
            mod['game_phases'] = csv_match.get('game_phases', {})
            csv_matched += 1
        else:
            mod.setdefault('authors', '')
            mod.setdefault('game_phases', {})
        
        # Use pending URL if no CSV URL
        if not mod.get('homepage') and not mod.get('github') and mod.get('url'):
            mod['github'] = mod.get('url', '')
        
        # Process each component
        mod['any_installed'] = False
        for comp in mod['components']:
            map_key = comp['map_key']
            pi_info = pi_map.get(map_key, {})
            
            # Store WeiDU generation data
            comp['weidu'] = {
                'folder': pi_info.get('folder', ''),
                'tp2_path': pi_info.get('tp2_path', ''),
                'comp_num': pi_info.get('comp', comp.get('comp_num', 0)),
                'confidence': pi_info.get('confidence', 'unknown'),
                'is_bgee': pi_info.get('is_bgee', mod['category'] == 'PRE EET BGEE MODS'),
                'pi_only': pi_info.get('pi_only', False),
            }
            
            # Check if installed
            folder = pi_info.get('folder', '').lower()
            comp_num = comp['weidu']['comp_num']
            inst_key = f"{folder}:{comp_num}"
            
            if inst_key in installed:
                comp['installed'] = True
                comp['installed_version'] = installed[inst_key]['version']
                mod['any_installed'] = True
                inst_matched += 1
            else:
                # Try direct tp2_base match for colon-format entries
                if comp['format'] == 'colon':
                    direct_key = f"{comp['tp2_base'].lower()}:{comp['comp_num']}"
                    for ik, iv in installed.items():
                        if ik == direct_key:
                            comp['installed'] = True
                            comp['installed_version'] = iv['version']
                            mod['any_installed'] = True
                            inst_matched += 1
                            break
                    else:
                        comp['installed'] = False
                        comp['installed_version'] = ''
                else:
                    comp['installed'] = False
                    comp['installed_version'] = ''
    
    print(f"   CSV matched: {csv_matched}/{len(mods)}")
    print(f"   Installed components matched: {inst_matched}")
    
    return mods


# ═══════════════════════════════════════════════════════════════
# 5. Build app-ready JSON
# ═══════════════════════════════════════════════════════════════

def build_app_data(mods):
    """Build compact JSON for the React app."""
    app_mods = []
    
    for m in mods:
        am = {
            'id': m['id'],
            'tp2': m['tp2_base'],
            'name': m['mod_name'],
            'cat': m['category'],
            'sub': m.get('subcategory', ''),
            'url': m.get('github') or m.get('homepage') or m.get('url') or '',
            'inst': m.get('any_installed', False),
            'notes': m.get('notes', ''),
        }
        
        if m.get('authors'): am['auth'] = m['authors']
        if m.get('requires'): am['req'] = m['requires']
        if m.get('incompatibilities'): am['ic'] = m['incompatibilities']
        
        ph = m.get('game_phases', {})
        phases = []
        if ph.get('bg1'): phases.append('BG1')
        if ph.get('sod'): phases.append('SoD')
        if ph.get('soa'): phases.append('SoA')
        if ph.get('tob'): phases.append('ToB')
        if phases: am['ph'] = phases
        
        comps = []
        for c in m['components']:
            ac = {
                'n': c['name'],
                'desc': c['full_desc'],
                'off': c['commented'],
                'inst': c.get('installed', False),
                'ver': c.get('installed_version', ''),
                'notes': c.get('notes', ''),
                # WeiDU generation data
                'w': {
                    'f': c['weidu']['folder'],
                    'p': c['weidu']['tp2_path'],
                    'c': c['weidu']['comp_num'],
                    'q': c['weidu']['confidence'],
                    'b': c['weidu']['is_bgee'],
                },
            }
            if c.get('pi_label'):
                ac['pi'] = c['pi_label']
            if c.get('comp_num') is not None:
                ac['num'] = c['comp_num']
            comps.append(ac)
        
        am['co'] = comps
        app_mods.append(am)
    
    return app_mods


def main():
    print("=" * 60)
    print("EET Mod Forge Data Pipeline v3")
    print("=" * 60)
    
    mods = merge_all()
    
    print("\n6. Building app data...")
    app_data = build_app_data(mods)
    
    total_comps = sum(len(m['co']) for m in app_data)
    installed_mods = sum(1 for m in app_data if m['inst'])
    installed_comps = sum(1 for m in app_data for c in m['co'] if c['inst'])
    with_url = sum(1 for m in app_data if m['url'])
    with_notes = sum(1 for m in app_data if m.get('notes'))
    
    cats = Counter(m['cat'] for m in app_data)
    
    print(f"\n   Final stats:")
    print(f"   Mods: {len(app_data)}")
    print(f"   Components: {total_comps}")
    print(f"   Installed mods: {installed_mods}")
    print(f"   Installed components: {installed_comps}")
    print(f"   With URLs: {with_url}")
    print(f"   With mod-level notes: {with_notes}")
    print(f"\n   Categories:")
    for cat, count in cats.most_common():
        print(f"     {count:4d}  {cat or '(none)'}")
    
    # Confidence distribution
    conf = Counter()
    for m in app_data:
        for c in m['co']:
            conf[c['w']['q']] += 1
    print(f"\n   WeiDU confidence:")
    for c, n in conf.most_common():
        print(f"     {n:4d}  {c}")
    
    outpath = '/home/claude/app_data_v3.json'
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(app_data, f, ensure_ascii=False, separators=(',', ':'))
    
    import os
    print(f"\n   Output: {outpath} ({os.path.getsize(outpath)/1024:.0f} KB)")


if __name__ == '__main__':
    main()
