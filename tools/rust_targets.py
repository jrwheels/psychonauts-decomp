"""Optional Rust relocation decoder; match selection remains in objmatch."""
import ctypes
from pathlib import Path
import struct


class RustTargets:
    def __init__(self, exe, library):
        self.exe = exe
        self.path = Path(library).resolve()
        self.library = ctypes.CDLL(str(self.path))
        self.library.psy_reloc_abi.argtypes = []
        self.library.psy_reloc_abi.restype = ctypes.c_uint32
        if self.library.psy_reloc_abi() != 1:
            raise ValueError("Unsupported Rust relocation ABI")
        self.decode = self.library.psy_reloc_targets
        self.decode.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint64,
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_size_t]
        self.decode.restype = ctypes.c_uint32
        self.text = ctypes.create_string_buffer(exe.text)

    def __call__(self, exe, fn, hits):
        if exe is not self.exe:
            raise ValueError("Rust relocation decoder belongs to another executable")
        # Preserve the oracle's Python slice behavior for unusual synthetic VAs.
        if not 0 <= exe.text_va <= 0xffffffffffffffff or any(
                not exe.text_va <= va <= 0xffffffffffffffff for va in hits):
            from objmatch import targets
            return [(va, targets(exe, fn, va)) for va in hits]
        relocs, code = fn.relocs(), fn.code
        if not hits or not relocs:
            return [(va, {}) for va in hits]
        if any(not 0 <= off <= 0xffffffff for off, _, _, _ in relocs):
            raise ValueError("Relocation offset outside the COFF range")
        n, cells = len(relocs), len(hits) * len(relocs)
        offsets = (ctypes.c_uint32 * n)(*(off for off, _, _, _ in relocs))
        kinds = (ctypes.c_uint32 * n)(*(kind for _, _, _, kind in relocs))
        addends = (ctypes.c_uint32 * n)(*(struct.unpack_from("<I", code, off)[0]
            if off + 4 <= len(code) else 0 for off, _, _, _ in relocs))
        addresses = (ctypes.c_uint64 * len(hits))(*hits)
        values, present = (ctypes.c_uint32 * cells)(), (ctypes.c_uint8 * cells)()
        if self.decode(self.text, len(exe.text), exe.text_va, addresses, len(hits),
                       offsets, kinds, addends, n, values, present, cells) != 0:
            raise ValueError("Rust relocation decoder rejected the batch")
        names = [name for _, _, name, _ in relocs]
        return [(va, {names[j]: values[i*n+j] for j in range(n) if present[i*n+j]})
                for i, va in enumerate(hits)]
