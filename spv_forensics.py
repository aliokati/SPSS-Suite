"""SPV Forensic Extractor - Recovers methodology and provenance."""
import zipfile
import xml.etree.ElementTree as ET
import re
from pathlib import Path
from light_table_reader import Reader

def clean_html(html):
    text = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    return re.sub(r'<[^>]+>', '', text).replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&nbsp;', ' ').strip()

def extract_syntax(z: zipfile.ZipFile):
    logs = []
    for xml_file in [f for f in z.namelist() if f.endswith('.xml') and 'outputViewer' in f]:
        xml_str = re.sub(rb'\sxmlns="[^"]+"', b'', z.read(xml_file), count=1)
        try:
            for node in ET.fromstring(xml_str).findall('.//text[@type="log"]'):
                clean = clean_html("".join(node.itertext()))
                if clean: logs.append(clean)
        except ET.ParseError: continue
    return logs

def get_text(cell):
    for k in ['string_hex', 'label_hex', 'local_hex']:
        if k in cell and cell[k]:
            try: return bytes.fromhex(cell[k]).decode('utf-8').strip()
            except: return bytes.fromhex(cell[k]).decode('windows-1252', errors='replace').strip()
    return str(cell.get('value', ''))

def extract_provenance(z: zipfile.ZipFile):
    prov = []
    for note_file in [f for f in z.namelist() if 'NotesData.bin' in f]:
        try:
            for cell in Reader(z.read(note_file)).parse()['cells']:
                path = cell['axis_coordinates']['rows'][0]['path']
                row_lbl = path[-1] if path else "Unknown"
                val = get_text(cell)
                if any(k in row_lbl for k in ["Data", "Dataset", "Filter", "Weight", "Split", "Syntax"]) and val:
                    prov.append((row_lbl, val))
        except Exception: continue
    return prov

def run_forensics(spv_path):
    path = Path(spv_path)
    if not path.exists(): return print(f"File {path} not found.")

    print(f"\n{'='*60}\n SPV FORENSIC REPORT: {path.name}\n{'='*60}\n")
    with zipfile.ZipFile(path, 'r') as z:
        print("--- 1. DATA PROVENANCE & ENVIRONMENT ---")
        prov = extract_provenance(z)
        if prov:
            for k, v in prov: print(f" {k:<20} | {v if len(v)<100 else v[:97]+'...'}")
        else: print(" No provenance metadata found.")
            
        print("\n--- 2. RECOVERED SPSS SYNTAX (METHODOLOGY) ---")
        logs = extract_syntax(z)
        if logs:
            for i, log in enumerate(logs, 1): print(f"\n[Block {i}]\n{'-'*40}\n{log}\n{'-'*40}")
        else: print(" No raw syntax logs found.")

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "real_output.spv"
    run_forensics(target)