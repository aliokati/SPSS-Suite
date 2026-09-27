"""Export parsed SPV Light Tables to Pandas DataFrames."""
import pandas as pd
from light_table_reader import Reader
from pathlib import Path

def flatten_spv_to_dataframe(parsed_table, join_char=" > "):
    rows = []
    for cell in parsed_table['cells']:
        row = {}
        for axis_name, dimensions in cell['axis_coordinates'].items():
            for dim in dimensions:
                # Use the last part of the path as the column name (e.g. Region, Gender, Statistics)
                col_name = "Category" # Default fallback
                if 'path' in dim and len(dim['path']) > 0:
                     col_name = dim['path'][0] if len(dim['path']) == 1 else " > ".join(dim['path'][:-1])
                row[col_name] = dim['label']
                
        row['Value'] = cell.get('value')
        row['Is_Missing'] = cell.get('is_missing', False)
        
        mod = cell.get('modifier', {})
        if mod.get('modified') and mod.get('footnote_refs'):
            row['Footnotes'] = ",".join(map(str, mod['footnote_refs']))
            
        rows.append(row)
    return pd.DataFrame(rows)