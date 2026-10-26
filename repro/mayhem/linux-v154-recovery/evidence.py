"""Static ELF reads for the single Mayhem distribution-data experiment."""
import hashlib
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Elf:
    def __init__(self, data):
        self.data = data
        require(data[:6] == b"\x7fELF\x02\x01", "Expected little-endian ELF64")
        require(len(data) >= 64, "Truncated ELF header")
        offset = struct.unpack_from("<Q", data, 40)[0]
        size, count, names_index = struct.unpack_from("<HHH", data, 58)
        require(size == 64 and 0 < names_index < count and offset + size * count <= len(data),
                "Invalid section table")
        self.rows = [struct.unpack_from("<IIQQQQIIQQ", data, offset + i * size) for i in range(count)]
        names_row = self.rows[names_index]
        names = self.read(names_row[4], names_row[5])
        self.sections = {}
        for row in self.rows:
            require(row[0] < len(names), "Invalid section name")
            name = names[row[0]:].split(b"\0", 1)[0].decode()
            require(name not in self.sections, "Duplicate section name")
            self.sections[name] = row
            if row[1] != 8:
                self.read(row[4], row[5])
        self.relocations = {}
        for row in self.rows:
            if row[1] == 9:
                require(row[9] == 16 and row[5] % 16 == 0, "Unexpected relocation shape")
                for at in range(row[4], row[4] + row[5], 16):
                    address, info = struct.unpack_from("<QQ", data, at)
                    require(address not in self.relocations, "Duplicate relocation address")
                    self.relocations[address] = info

    def read(self, offset, size):
        require(0 <= offset <= len(self.data) and 0 <= size <= len(self.data) - offset, "Out-of-bounds ELF read")
        return self.data[offset:offset + size]

    def offset(self, address, size=1):
        matches = [r[4] + address - r[3] for r in self.rows
                   if r[2] & 2 and r[1] != 8 and r[3] <= address and address + size <= r[3] + r[5]]
        require(len(matches) == 1, "Address does not select one allocated section")
        return matches[0]

    def allocated(self):
        return {name: (r[3], r[5], r[1], self.read(r[4], r[5]))
                for name, r in self.sections.items() if r[2] & 2 and r[1] != 8}

    def location(self, instruction_address):
        at = self.offset(instruction_address, 16)
        code = self.read(at, 16)
        require(code[0] == 0x18 and code[8:12] == b"\0" * 4, "Expected relocated LDDW")
        require(self.relocations.get(instruction_address) == 8, "Missing instruction relocation")
        target = struct.unpack_from("<I", code, 4)[0] | struct.unpack_from("<I", code, 12)[0] << 32
        record = self.read(self.offset(target, 24), 24)
        require(self.relocations.get(target) == 8, "Missing Location pointer relocation")
        pointer, length, line, column = struct.unpack("<QQII", record)
        require(pointer & 0xffffffff == 0 and 0 < length < 1024, "Unexpected stored V0 data pointer")
        pointer >>= 32
        raw_path = self.read(self.offset(pointer, length), length)
        return {"reference_pc": instruction_address, "reference_raw": code.hex(),
                "location_record": target, "record_raw": record.hex(), "file_pointer": pointer,
                "file_length": length, "file_raw_hex": raw_path.hex(),
                "file_display": raw_path.rstrip(b"\0").decode("utf-8"), "line": line, "column": column}

    def constructor_locations(self):
        row = self.sections.get(".symtab")
        require(row is not None and row[9] == 24, "Missing full symbol table")
        require(row[6] < len(self.rows), "Invalid symbol strings")
        strings_row = self.rows[row[6]]
        strings = self.read(strings_row[4], strings_row[5])
        found = []
        for at in range(row[4], row[4] + row[5], 24):
            name_index, info, _, section, address, size = struct.unpack_from("<IBBHQQ", self.data, at)
            require(name_index < len(strings), "Invalid symbol name")
            name = strings[name_index:].split(b"\0", 1)[0].decode()
            if info & 15 != 2 or not size or "anchor_lang..error..ErrorCode" not in name or "$GT$4from" not in name:
                continue
            self.offset(address, size)
            for pc in range(address, address + size, 8):
                if self.relocations.get(pc) != 8 or self.data[self.offset(pc)] != 0x18:
                    continue
                try:
                    location = self.location(pc)
                except (ValueError, UnicodeError):
                    continue
                if location["file_display"].endswith("/alloc/src/string.rs"):
                    found.append({"symbol": name, "function_start": address, "function_bytes": size,
                                  "location": location})
        require(len(found) == 1, "Expected one ErrorCode conversion alloc-string Location")
        return found[0]


def compare(first, second):
    shared = min(len(first), len(second))
    changed = sum(a != b for a, b in zip(first, second))
    return {"reference_sha256": sha(first), "candidate_sha256": sha(second),
            "reference_bytes": len(first), "candidate_bytes": len(second),
            "differing_shared_positions": changed, "length_difference": len(second) - len(first),
            "first_difference": next((i for i in range(shared) if first[i] != second[i]),
                                     shared if len(first) != len(second) else None),
            "full_byte_equality": first == second}


def same_location_payload(first, second):
    return all(first[key] == second[key] for key in ("file_raw_hex", "file_length", "line", "column"))
