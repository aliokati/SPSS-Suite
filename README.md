
# SPSS Viewer (.spv) Forensic Suite

A comprehensive toolkit for generating, parsing, and performing forensic analysis on SPSS Viewer files using pure Python.

## Features
- **LightTableWriter**: Programmatic creation of SPV files with support for 3D hierarchical layers, sparse coordinates, custom formatting, and cell styling.
- **LightTableReader**: Deep binary parsing of v3 SPV members, including system-missing sentinel detection and labeled numeric data (Tag 2/4).
- **Pandas Exporter**: Seamless extraction of hierarchical SPV table data into "tidy" Pandas DataFrames.
- **Forensic Extractor**: Recovers methodology (SPSS syntax logs) and data provenance (file paths, filters, weights) from hidden "Notes" tables and XML logs within the SPV container.

## Usage
- **Parse/Extract**: `python spv_forensics.py <your_file.spv>`
- **DataFrame Export**: `python spv_to_pandas.py`

*Note: No external dependencies required for parsing, pandas is required for CSV/DataFrame export.*