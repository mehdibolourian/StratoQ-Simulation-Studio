"""Synthetic Mach-O tests. No SciPy or macOS required."""
import importlib.util
from pathlib import Path
import struct
import subprocess
import tempfile
from unittest import mock

MODULE = Path(__file__).resolve().parents[2] / 'scripts' / 'repair_macos_scipy.py'
spec = importlib.util.spec_from_file_location('repair_macos_scipy', MODULE)
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def build_macho(*, bad_offset=488, flags=0x12, cputype=repair.ARM64_CPUTYPE):
    a = bytearray(600)
    a[:4] = repair.MAGIC_64_LE
    struct.pack_into('<I', a, 4, cputype)
    struct.pack_into('<I', a, 16, 1)  # ncmds
    struct.pack_into('<I', a, 20, 72 + 80) # sizeofcmds
    struct.pack_into('<II', a, 32, repair.LC_SEGMENT_64, 72 + 80)
    struct.pack_into('<I', a, 32 + 64, 1) # nsects
    section = 32 + 72
    a[section:section + 12] = b'__thread_bss'
    struct.pack_into('<I', a, section + 48, bad_offset)
    struct.pack_into('<I', a, section + 64, flags)
    return a


def test_detect_bad_thread_bss():
    assert repair.zero_fill_offsets(build_macho()) == [32 + 72 + 48]


def test_zeros_and_regular_section_untouched():
    assert repair.zero_fill_offsets(build_macho(bad_offset=0)) == []
    assert repair.zero_fill_offsets(build_macho(flags=0)) == []
    assert repair.zero_fill_offsets(build_macho(cputype=0x01000007)) == []
    assert repair.zero_fill_offsets(b'ELF' + b'\0' * 100) == []


def test_reject_corrupt_load_command():
    d = build_macho()
    struct.pack_into('<I', d, 32 + 4, 5000)
    try:
        repair.zero_fill_offsets(d)
    except repair.MalformedMachO:
        return
    raise AssertionError('Expected malformed Mach-O rejection')


def test_backup_repair_and_resign():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / 'scipy'
        root.mkdir()
        so = root / '_spropack.so'
        raw = bytes(build_macho())
        so.write_bytes(raw)
        with mock.patch.object(repair.sys, 'platform', 'darwin'), mock.patch.object(repair.subprocess, 'run') as run:
            modified = repair.repair_file(so, root, Path(tmp)/'backups', repair=True)
        assert modified == 1
        assert repair.zero_fill_offsets(so.read_bytes()) == []
        assert b'__thread_bss' in so.read_bytes()
        assert list((Path(tmp)/'backups').rglob('*.original'))[0].read_bytes() == raw
        assert run.call_count == 2
        assert run.call_args_list[0].args[0][:3] == ['codesign','--force','--sign']


def test_roll_back_on_sign_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)/'scipy'
        root.mkdir()
        so = root / '_spropack.so'
        raw = bytes(build_macho())
        so.write_bytes(raw)
        with mock.patch.object(repair.sys, 'platform','darwin'), mock.patch.object(repair.subprocess,'run',side_effect=subprocess.CalledProcessError(1,'codesign')):
            try:
                repair.repair_file(so,root,Path(tmp)/'backups',repair=True)
            except subprocess.CalledProcessError:
                pass
            else:
                raise AssertionError('Expected codesign failure')
        assert so.read_bytes() == raw
