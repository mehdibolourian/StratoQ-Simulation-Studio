#!/usr/bin/env python3
"""Repair malformed zero-fill Mach-O section offsets in *project venv SciPy*.

This is a narrow workaround for macOS dyld rejecting selected Python 3.10
SciPy wheels with e.g. __DATA/__thread_bss offset!=0. Only changes 4-byte
section offset fields to 0 and ad-hoc re-signs changed SciPy extension files.
Original files are backed up before changes, and restored if signing fails.
Does not alter anything in Conda base, Gurobi, Balloon-QNet, or LOWTRAN.
"""

import argparse
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import sysconfig

ARM64_CPUTYPE = 0x0100000C
LC_SEGMENT_64 = 0x19
ZEROFILL_SECTION_TYPES = {0x1, 0xC, 0x12}
MAGIC_64_LE = b'\xcf\xfa\xed\xfe'


class MalformedMachO(Exception):
    pass


def zero_fill_offsets(data):
    """Return byte positions of nonzero zero-fill section offsets in thin ARM64 Mach-O."""
    if data[:4] != MAGIC_64_LE:
        return []  # no modification of non-arm64, universal, or non-Mach-O files
    if len(data) < 32:
        raise MalformedMachO('truncated mach_header_64')
    cputype = struct.unpack_from('<I', data, 4)[0]
    ncmds = struct.unpack_from('<I', data, 16)[0]
    sizeofcmds = struct.unpack_from('<I', data, 20)[0]
    if cputype != ARM64_CPUTYPE:
        return []
    limit = 32 + sizeofcmds
    if limit > len(data):
        raise MalformedMachO('load commands extend beyond file')
    off = 32
    fixes = []
    for _ in range(ncmds):
        if off + 8 > limit:
            raise MalformedMachO('truncated load command')
        cmd, size = struct.unpack_from('<II', data, off)
        if size < 8 or off + size > limit:
            raise MalformedMachO('invalid load command size')
        if cmd == LC_SEGMENT_64:
            if size < 72:
                raise MalformedMachO('truncated segment_command_64')
            nsects = struct.unpack_from('<I', data, off + 64)[0]
            if nsects > (size - 72) // 80:
                raise MalformedMachO('segment sections exceed command')
            for i in range(nsects):
                section = off + 72 + i * 80
                flags = struct.unpack_from('<I', data, section + 64)[0]
                old_offset = struct.unpack_from('<I', data, section + 48)[0]
                if (flags & 0xFF) in ZEROFILL_SECTION_TYPES and old_offset != 0:
                    fixes.append(section + 48)
        off += size
    return fixes


def repair_file(path, scipy_root, backup_root, repair):
    data = bytearray(path.read_bytes())
    offsets = zero_fill_offsets(data)
    if not offsets:
        return 0
    if path.is_symlink() or not path.resolve().is_relative_to(scipy_root.resolve()):
        raise MalformedMachO('SciPy extension path escapes the project environment')
    rel = path.relative_to(scipy_root)
    if not repair:
        print(f'NEEDS REPAIR: scipy/{rel} ({len(offsets)} section(s))', flush=True)
        return len(offsets)
    if not sys.platform.startswith('darwin'):
        raise RuntimeError('macOS-only modification refused on this platform')
    digest = hashlib.sha256(data).hexdigest()[:12]
    backup = backup_root / rel.parent / (rel.name + '.' + digest + '.original')
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(path, backup)
    original = bytes(data)
    for pos in offsets:
        struct.pack_into('<I', data, pos, 0)
    try:
        with path.open('wb') as f:
            f.write(data)
        shutil.copymode(backup, path)
        subprocess.run(['codesign', '--force', '--sign', '-', str(path)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        subprocess.run(['codesign', '--verify', str(path)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except Exception:
        # A failed re-sign leaves an unusable extension. Restore the exact old bytes.
        with path.open('wb') as f:
            f.write(original)
        shutil.copymode(backup, path)
        raise
    print(f'REPAIRED: scipy/{rel} ({len(offsets)} section(s)); original backed up', flush=True)
    return len(offsets)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true', help='List malformed sections without modifying files')
    group.add_argument('--repair', action='store_true', help='Backup, patch and ad-hoc sign affected SciPy libraries')
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    expected_venv = (root / 'backend' / '.venv').resolve()
    actual_venv = Path(sys.prefix).resolve()
    if actual_venv != expected_venv or sys.prefix == sys.base_prefix:
        print('ERROR: refusing to touch anything outside this project backend/.venv', file=sys.stderr)
        return 2
    if args.repair and sys.platform != 'darwin':
        print('ERROR: repair supported only on macOS', file=sys.stderr)
        return 2
    scipy_root = Path(sysconfig.get_path('purelib')) / 'scipy'
    if not scipy_root.is_dir() or not scipy_root.resolve().is_relative_to(expected_venv):
        print('ERROR: SciPy package not installed inside backend/.venv', file=sys.stderr)
        return 2
    backup_root = expected_venv / '.stratoq-native-backups' / 'scipy'
    num = 0
    nfiles = 0
    for so in sorted(scipy_root.rglob('*.so')):
        try:
            touched = repair_file(so, scipy_root, backup_root, args.repair)
        except (OSError, RuntimeError, MalformedMachO, subprocess.CalledProcessError) as exc:
            print(f'ERROR: failed processing {so}: {exc}', file=sys.stderr)
            return 1
        if touched:
            nfiles += 1
            num += touched
    print(f'SciPy Mach-O inspection: {nfiles} file(s), {num} section offset(s) '
          f'{"repaired" if args.repair else "requiring repair"}.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
