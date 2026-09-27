"""Sequential SPV light-table v3 reader."""
import json, struct, codecs
from pivot_geometry import unflatten_index

class ParseError(ValueError): pass

class Reader:
    def __init__(self, data):
        self.data, self.offset, self.trace, self.strings, self.encoding = data, 0, [], [], 'windows-1252'
    def take(self, n):
        if n > len(self.data) - self.offset: raise ParseError('Truncated')
        self.offset += n; return self.data[self.offset-n:self.offset]
    def number(self, fmt): return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]
    def u8(self): return self.number('<B')
    def u32(self): return self.number('<I')
    def u64(self): return self.number('<Q')
    def double(self): return self.number('<d')
    def optional(self, byte):
        if self.data[self.offset:self.offset+1] == bytes([byte]):
            self.offset += 1; return True
        return False
    def count(self, min=1): return self.u32()
    def string(self):
        n = self.u32(); val = self.take(n); self.strings.append({'hex': val.hex()}); return val
    def opaque(self, name): self.trace.append({'section': name, 'raw_bytes': self.take(self.u32()).hex()})

    @staticmethod
    def label(value):
        tag = value['tag']
        def text(hex_str): return bytes.fromhex(hex_str).decode('utf-8', 'replace')
        if tag in (3, 6): return text(value['local_hex'])
        if tag == 5: return text(value['label_hex']) or text(value['variable_hex'])
        if tag in (2, 4): return text(value['label_hex']) or str(value.get('value', text(value.get('string_hex',''))))
        if tag == 1: return str(value['value'])
        return text(value.get('template_hex', ''))

    def mod(self, tag=None):
        if (tag or self.u8()) == 0x58: return {'modified': False}
        return {'modified': True, 'footnote_refs': [self.number('<H') for _ in range(self.count(2))],
                'subscripts_hex': [self.string().hex() for _ in range(self.count(4))], 'style_payload_hex': self.take(self.u32()).hex()}

    def _value(self):
        start = self.offset
        while self.optional(0): pass
        tag = self.u8()
        res = {'start': start, 'tag': tag}
        if tag in (1, 2):
            res['modifier'], res['format'] = self.mod(), self.u32()
            raw_val = self.double()
            res['is_missing'] = (raw_val == -float.fromhex('0x1.fffffffffffffp+1023') or (res['modifier'].get('modified') and raw_val < -1e307))
            res['value'] = None if res['is_missing'] else raw_val
            if tag == 2: res['variable_hex'], res['label_hex'], res['show'] = self.string().hex(), self.string().hex(), self.u8()
        elif tag in (3, 6):
            res['local_hex'], res['modifier'], res['id_hex'], res['english_hex'] = self.string().hex(), self.mod(), self.string().hex(), self.string().hex()
            if tag == 3: res['fixed'] = self.u8()
        elif tag == 4:
            res['modifier'], res['format'], res['label_hex'], res['variable_hex'], res['show'], res['string_hex'] = self.mod(), self.u32(), self.string().hex(), self.string().hex(), self.u8(), self.string().hex()
        elif tag == 5:
            res['modifier'], res['variable_hex'], res['label_hex'], res['show'] = self.mod(), self.string().hex(), self.string().hex(), self.u8()
        elif tag in (0x31, 0x58):
            res['modifier'], res['template_hex'] = self.mod(tag), self.string().hex()
            res['arguments'] = [[self._value() for _ in range(self.u32() or 1)] for _ in range(self.count(4))]
        return res

    def category(self):
        val = self._value()
        node = {'name': val, 'label': self.label(val)}
        if self.take(4) == b'\xff'*4:
            node.update(kind='group', flatten=bool(self.u8()), children=[(self.take(6), self.category())[1] for _ in range(self.count())])
            self.take(4)
        else:
            idx = struct.unpack('<I', self.take(6)[2:6])[0]
            node.update(kind='leaf', leaf_index=-1 if idx == 0xffffffff else idx)
            self.take(4)
        return node

    def parse(self):
        self.take(22)
        table_id = self.u64()
        title, user_title = self._value(), (self.take(2), self._value())[1]
        self.take(13); [self._value() for _ in range(self.count())]
        for _ in range(8): self.take(10); self.string(); self.take(13); self.string(); self.string(); self.take(17)
        for name in ('Borders', 'PrintSettings', 'TableSettings'): self.opaque(name)
        self.take(self.count(4)*4); self.string(); self.take(12); [self.string() for _ in range(self.count(4))]
        self.opaque('Formats extension')
        dims = []
        for _ in range(self.count()):
            name, x1, x2, x3 = self._value(), self.u8(), self.u8(), self.u32()
            flags = self.take(2)
            self.take(1)
            dims.append({'name': name, 'label': self.label(name), 'dim_index': self.u32(), 'hide_dim_label': bool(flags[0]), 'categories': [self.category() for _ in range(self.count())]})
        axes = [self.u32() for _ in range(3)]
        order = [self.u32() for _ in range(sum(axes))]
        ax_dims = {'layers': order[:axes[0]], 'rows': order[axes[0]:axes[0]+axes[1]], 'columns': order[axes[0]+axes[1]:]}
        cells = [{'index': self.u64(), **self._value()} for _ in range(self.count(9))]
        
        maps = []
        for dim in dims:
            leaves = []
            def visit(nodes, path):
                for n in nodes: visit(n['children'], path+[n['label']]) if n['kind'] == 'group' else leaves.append({'index': n['leaf_index'], 'label': n['label'], 'path': path+[n['label']]})
            visit(dim['categories'], [])
            mapping = {l['index']: l for l in leaves}
            dim['cardinality'] = len(leaves)
            maps.append(mapping)
            
        sizes = [d['cardinality'] for d in dims]
        for c in cells:
            coords = unflatten_index(c['index'], sizes)
            c['coordinates'] = coords
            c['axis_coordinates'] = {ax: [{'label': maps[d][coords[d]]['label'], 'path': maps[d][coords[d]]['path']} for d in dms] for ax, dms in ax_dims.items()}
            
        return {'table_id': table_id, 'title': self.label(user_title), 'dimensions': dims, 'cells': cells}