"""Generate numeric SPV light tables from arrays, with multiple layers, missing values, and strings."""
import math
import secrets
import struct
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from collections.abc import Mapping
from pivot_geometry import flatten_index

SYSTEM_MISSING = -float.fromhex('0x1.fffffffffffffp+1023')

def u32(n): return struct.pack('<I', n)
def be32(n): return struct.pack('>I', n)
def u64(n): return struct.pack('<Q', n)
def f64(n): return struct.pack('<d', n)
def counted(data): return u32(len(data)) + data
def be_counted(data): return be32(len(data)) + data

def string(text):
    if not isinstance(text, str): raise TypeError('Labels must be strings')
    if '\0' in text: raise ValueError('Embedded NUL in label')
    return counted(text.encode('utf-8'))

def text_value(text):
    return b'\x03' + string(text) + b'\x58' + string('') + string(text) + b'\x01'

def category_tree(nodes):
    leaves, active = [], set()
    def visit(items, depth=0):
        if depth > 64: raise ValueError('Category nesting exceeds 64 levels')
        result = []
        for item in items:
            if isinstance(item, str): item = {'label': item}
            if id(item) in active: raise ValueError('Cyclic category hierarchy')
            label = item.get('label')
            string(label)
            node = {'label': label}
            if 'children' in item:
                flatten = item.get('flatten', False)
                active.add(id(item))
                node.update(kind='group', flatten=flatten, children=visit(item['children'], depth+1))
                active.remove(id(item))
            else:
                index = item.get('leaf_index')
                node.update(kind='leaf', leaf_index=index)
                leaves.append(node)
            result.append(node)
        return result
    forest = visit(nodes)
    explicit = [n['leaf_index'] for n in leaves if n['leaf_index'] is not None]
    used = set(explicit)
    available = iter(i for i in range(len(leaves)) if i not in used)
    for leaf in leaves:
        if leaf['leaf_index'] is None: leaf['leaf_index'] = next(available)
    return forest, len(leaves)

def parse_cell(value, default_decimals=3):
    footnotes, style, label = [], b'', None
    decimals = default_decimals
    
    if isinstance(value, dict):
        footnotes = value.get('footnotes', [])
        style = value.get('style', b'')
        decimals = value.get('decimals', default_decimals)
        label = value.get('label')
        value = value.get('value')
        
    if value is None:
        return ('missing', SYSTEM_MISSING, footnotes, style, decimals, None)
    if isinstance(value, str):
        return ('string', value, footnotes, style, decimals, None)
    
    value = float(value)
    if not math.isfinite(value) and value != SYSTEM_MISSING:
        raise ValueError('Non-finite cells are unsupported')
        
    if label is not None:
        return ('labeled', value, footnotes, style, decimals, label)
    return ('numeric', value, footnotes, style, decimals, None)

class LightTableWriter:
    def __init__(self, data, row_labels, column_labels, layer_labels=None,
                 row_name='Gender', column_name='Region', layer_name='Statistics',
                 title='Custom Table', decimals=3, table_id=None, timestamp=None):
        if layer_labels is None: layer_labels = ['Count']
        self.rows, n_rows = category_tree(row_labels)
        self.columns, n_columns = category_tree(column_labels)
        self.layers, n_layers = category_tree(layer_labels)
        self.shape = (n_rows, n_columns, n_layers)
        self.row_name, self.column_name, self.layer_name, self.title = row_name, column_name, layer_name, title
        self.decimals = decimals
        
        populated = {}
        if isinstance(data, Mapping):
            for coordinate, value in data.items():
                coord_3d = coordinate if len(coordinate) == 3 else (*coordinate, 0)
                index = flatten_index(coord_3d, self.shape)
                populated[index] = parse_cell(value, decimals)
        else:
            for r, row in enumerate(data):
                for col, value in enumerate(row):
                    populated[flatten_index((r, col, 0), self.shape)] = parse_cell(value, decimals)
        
        self.populated = dict(sorted(populated.items()))
        self.table_id = (secrets.randbits(63) or 1) if table_id is None else table_id
        self.timestamp = int(time.time()) if timestamp is None else timestamp

    def header(self): return b'\x01\x00' + u32(3) + bytes([1,0,0,0,1]) + b''.join(u32(n) for n in [21,67,96,48,160]) + u64(self.table_id)
    def titles(self): return text_value(self.title) + text_value('Custom Table') + b'\x31' + text_value(self.title) + b'\x58\x58'
    
    def areas(self):
        res = bytearray()
        for idx in range(1,9):
            res += bytes([idx,0x31]) + string('SansSerif') + struct.pack('<f',14 if idx==1 else 12) + u32(1 if idx==1 else 0) + b'\x00' + u32(4 if idx==7 else 2) + u32(1) + string('#000000') + string('#ffffff') + b'\x00' + string('') + string('') + b''.join(u32(n) for n in [8,8,2,2])
        return bytes(res)

    def borders(self): return counted(be32(1)+be32(19)+b''.join(be32(i)+be32(1)+be32(0xff808080) for i in range(19))+b'\x00'*4)
    def print_settings(self): return counted(be32(1)+bytes([0,0,1,0,0,0])+be32(2)+be_counted(b''))
    def table_settings(self): return counted(be32(1)+be32(4)+be32(0)+bytes([0,0,0,1,0])+be_counted(be32(0)*6)+be_counted(b'')+be_counted(b'')+b'\x00'*82)

    def formats(self):
        loc = 'en_US.UTF-8'
        epoch = u32(1957)+b'.,'
        currency = u32(5)+string('-,,,')*5
        n1 = bytes([0,1,0,0,2,2])+u32(0xffffffff)*2+b'\x00'*17+bytes([0,0])
        n2 = u32(0)*3+counted(b'')
        y1 = b''.join(string(s) for s in ['Custom Table','Custom Table','en','UTF-8',loc]) + bytes([0,1,1,1])+epoch
        n3 = bytes([1,0,4,0,0,0])+y1+f64(0.0001)+b'\x01'+string('')*3+u32(self.timestamp)+u32(0)+currency+b'.\x00'+u32(0)*2+b'\x01'
        return u32(0)+string(loc)+u32(0)+b'\x00'*3+epoch+currency+counted(counted(n1+counted(n2))+counted(n3))

    def category(self, node):
        name = text_value(node['label'])
        if node['kind'] == 'leaf': return name+b'\x00'*3+u32(2)+u32(node['leaf_index'])+u32(0)
        return name+bytes([int(node['flatten']),0,1])+u32(0)+u32(0xffffffff)+u32(len(node['children']))+b''.join(self.category(c) for c in node['children'])

    def dimension(self, name, categories, pos, x2):
        return text_value(name)+bytes([0,x2])+u32(2)+bytes([0,0,1])+u32(pos)+u32(len(categories))+b''.join(self.category(n) for n in categories)

    def dimensions(self): return u32(3)+self.dimension(self.row_name,self.rows,0,2)+self.dimension(self.column_name,self.columns,1,0)+self.dimension(self.layer_name,self.layers,2,1)
    def axes(self): return b''.join(u32(n) for n in [1,1,1,2,0,1])

    def cells(self):
        payload = bytearray(u32(len(self.populated)))
        for index, (ctype, value, footnotes, style, decs, label) in self.populated.items():
            payload += u64(index)
            cell_format = (5 << 16) | (40 << 8) | decs
            has_mod = bool(footnotes or style or ctype == 'missing')
            mod_flag = b'\x31' if has_mod else b'\x58'
            mod_bytes = b''
            if has_mod:
                mod_bytes = u32(len(footnotes)) + b''.join(struct.pack('<H', f) for f in footnotes) + u32(0) + u32(len(style)) + style
                
            if ctype in ('missing', 'numeric'):
                payload += b'\x01' + mod_flag + mod_bytes + u32(cell_format) + f64(value)
            elif ctype == 'labeled':
                payload += b'\x02' + mod_flag + mod_bytes + u32(cell_format) + f64(value) + string('') + string(label) + bytes([2])
            elif ctype == 'string':
                str_format = (1 << 16) | (min(255, max(1, len(value))) << 8) | 0
                payload += b'\x04' + mod_flag + mod_bytes + u32(str_format) + string(value) + string('') + bytes([1]) + string(value)
        return bytes(payload)

    def to_bytes(self):
        for label in [self.row_name, self.column_name, self.layer_name, self.title]: string(label)
        return self.header()+self.titles()+u32(0)+self.areas()+self.borders()+self.print_settings()+self.table_settings()+self.formats()+self.dimensions()+self.axes()+self.cells()

    def write_spv(self, path):
        path = Path(path)
        member = '00000000001_lightTableData.bin'
        xml = f'''<?xml version="1.0" encoding="utf-8"?>
<heading xmlns="http://xml.spss.com/spss/viewer/viewer-tree" creator-version="27000100">
  <label>Output</label>
  <heading commandName="Custom Table"><label>Custom Table</label>
    <container visibility="visible"><label>{self.title}</label>
      <table tableId="{self.table_id if self.table_id < 1<<63 else self.table_id-(1<<64)}" subType="Custom Table" type="table">
        <tableStructure xmlns="http://xml.spss.com/spss/viewer/viewer-table"><dataPath>{member}</dataPath></tableStructure>
      </table>
    </container>
  </heading>
</heading>'''
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(member, self.to_bytes())
            z.writestr('outputViewer0000000000_heading.xml', xml)
            z.writestr('META-INF/MANIFEST.MF', b'allowPivoting=true\n')
        return path