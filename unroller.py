"""Reconstruct perfect categorical microdata from a parsed SPV crosstab."""
import pandas as pd
import json
import argparse
from pathlib import Path

def unroll_crosstab(parsed_table):
    """
    Takes a parsed SPV crosstab (with a Count statistic) and reconstructs 
    the raw row-level microdata.
    """
    raw_rows = []
    
    # 1. Verify this is a Count table
    has_count = False
    for cell in parsed_table.get('cells', []):
        for axis_val in cell.get('axis_coordinates', {}).values():
            for dim in axis_val:
                if dim.get('label') == 'Count':
                    has_count = True
                    break
            if has_count: break
        if has_count: break
        
    if not has_count:
        raise ValueError("Cannot unroll this table. No 'Count' statistic found.")
        
    # 2. Iterate through cells and unroll
    for cell in parsed_table.get('cells', []):
        # We only want raw cells, not marginal totals.
        # Check if any dimension path ends with 'Total'
        is_marginal = False
        row_data = {}
        
        for axis_name, dimensions in cell.get('axis_coordinates', {}).items():
            for dim in dimensions:
                # Skip the Statistics layer itself
                if dim.get('dimension_label') == 'Statistics':
                    continue
                    
                label = dim.get('label')
                if label == 'Total' or (dim.get('path') and 'Total' in dim['path']):
                    is_marginal = True
                    break
                    
                col_name = dim.get('dimension_label')
                row_data[col_name] = label
                
            if is_marginal: break
            
        # If it's a valid interior cell, append N copies of it
        if not is_marginal and cell.get('value') is not None:
            count = int(cell['value'])
            for _ in range(count):
                raw_rows.append(row_data.copy())
                
    return pd.DataFrame(raw_rows)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Unroll an SPV crosstab into raw microdata.")
    parser.add_argument('json_file', type=Path, help="JSON dump of parsed SPV (e.g. from light_table_reader.py)")
    args = parser.parse_args()
    
    data = json.loads(args.json_file.read_text())
    
    # Find the first parsed table
    target_table = None
    if 'cells' in data: # Direct table dump
        target_table = data
    else: # Archive dump
        for key, val in data.items():
            if isinstance(val, dict) and 'cells' in val:
                target_table = val
                break
                
    if not target_table:
         print("Error: No valid parsed table data found in JSON.")
    else:
        df = unroll_crosstab(target_table)
        print(f"\n--- Reconstructed Microdata ({len(df)} rows) ---")
        print(df)
        
        out_path = args.json_file.with_suffix('.csv')
        df.to_csv(out_path, index=False)
        print(f"\nSaved raw data to {out_path}")
```eof

```python:02_case_summary_extractor.py
"""Recover continuous microdata from literal case listings in SPV."""
import pandas as pd
import json
import argparse
from pathlib import Path

def extract_case_summaries(parsed_table):
    """
    Extracts raw microdata from SUMMARIZE or LIST command outputs where
    each row in the pivot grid represents a literal case.
    """
    rows = []
    
    # In Case Summaries, the 'Row' axis usually represents the Case Number
    # and the 'Column' axis represents the Variables.
    for cell in parsed_table.get('cells', []):
        is_marginal = False
        
        # Filter out "Total" rows
        for dim in cell.get('axis_coordinates', {}).get('rows', []):
            if 'Total' in dim.get('path', []):
                is_marginal = True
                
        if is_marginal: continue
        
        # Build the coordinate
        case_id = cell['axis_coordinates']['rows'][0]['label']
        variable = cell['axis_coordinates']['columns'][0]['label']
        value = cell.get('value')
        
        rows.append({
            'Case': case_id,
            'Variable': variable,
            'Value': value
        })
        
    flat_df = pd.DataFrame(rows)
    # Pivot to standard wide format
    return flat_df.pivot(index='Case', columns='Variable', values='Value').reset_index()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Extract raw data from SPV Case Summaries.")
    parser.add_argument('json_file', type=Path, help="JSON dump of parsed SPV")
    args = parser.parse_args()
    
    data = json.loads(args.json_file.read_text())
    
    target_table = data if 'cells' in data else next((v for v in data.values() if isinstance(v, dict) and 'cells' in v), None)
            
    if not target_table:
         print("Error: No valid parsed table data found.")
    else:
        df = extract_case_summaries(target_table)
        print(f"\n--- Extracted Case Data ({len(df)} rows) ---")
        print(df)
```eof

### Implementation Notes
1. **`01_categorical_unroller.py`**: This script targets the **Tier 2** methodology. It takes the parsed JSON output from a `CROSSTABS` output (like the output of your `03_coordinate_map.json`), ignores the marginal "Total" columns, reads the integer count (e.g., `3.0`), and dynamically spawns exactly 3 identical rows in a Pandas DataFrame (e.g., `["Female", "North"]`).
2. **`02_case_summary_extractor.py`**: This script targets the **Tier 1** methodology. It looks for SPV outputs generated by the SPSS `SUMMARIZE` or `LIST` commands, which leak continuous values row-by-row. It extracts the raw cell value and pivots the structural layout back into a standard tabular DataFrame, effectively rescuing continuous microdata.

To test the categorical unroller, simply point it at the JSON you generated earlier:
`python 01_categorical_unroller.py 03_coordinate_map.json`

This will generate a `.csv` file containing the exact 10 original rows of microdata that you used to generate that crosstab in SPSS!
