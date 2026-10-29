#!/usr/bin/env python3
"""Targeted macOS trust/signature repair for StratoQ's bundled LOWTRAN7 extension.

This script does not alter native code, change the solver, or weaken system-wide
macOS security. It only removes quarantine (when present) from the known,
project-local LOWTRAN extension and applies an ad-hoc signature. The original is
backed up, and failed signing restores the original file and metadata.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig


def run(argv):
    return subprocess.run(argv, capture_output=True, text=True)


def target_and_backup():
    root = Path(__file__).resolve().parents[1]
    backend = root / 'backend'
    venv = (backend / '.venv').resolve()
    if Path(sys.prefix).resolve() != venv or sys.prefix == sys.base_prefix:
        raise RuntimeError('refusing to run outside this project backend/.venv')
    if sys.version_info[:2] != (3, 10):
        raise RuntimeError('bundled LOWTRAN requires CPython 3.10')
    suffix = sysconfig.get_config_var('EXT_SUFFIX')
    if suffix != '.cpython-310-darwin.so':
        raise RuntimeError('expected the CPython 3.10 macOS LOWTRAN extension suffix')
    directory = backend / 'balloon_qnet' / 'lowtran_piccia'
    target = directory / ('lowtran7' + suffix)
    if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(directory.resolve()):
        raise RuntimeError(f'expected a regular, project-local LOWTRAN binary: {target}')
    digest = hashlib.sha256(target.read_bytes()).hexdigest()[:16]
    backup = venv / '.stratoq-native-backups' / 'lowtran' / (target.name + '.' + digest + '.original')
    return target, backup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true', help='Inspect the signature and quarantine without modifying the binary')
    group.add_argument('--repair', action='store_true', help='Back up, unquarantine and ad-hoc sign the bundled LOWTRAN extension')
    args = parser.parse_args(argv)
    if sys.platform != 'darwin':
        print('ERROR: macOS only', file=sys.stderr)
        return 2
    try:
        target, backup = target_and_backup()
    except (OSError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

    signature = run(['codesign', '--verify', '--verbose=2', str(target)])
    quarantine = run(['xattr', '-p', 'com.apple.quarantine', str(target)])
    is_quarantined = quarantine.returncode == 0
    print(f'LOWTRAN: {target}', flush=True)
    print(f'Existing signature verification: {"PASS" if signature.returncode == 0 else "FAIL"}', flush=True)
    print(f'Quarantine attribute: {"PRESENT" if is_quarantined else "absent"}', flush=True)
    if args.check:
        return 0

    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(target, backup)
    print(f'Original backed up to: {backup}', flush=True)
    try:
        if is_quarantined:
            removed = run(['xattr', '-d', 'com.apple.quarantine', str(target)])
            if removed.returncode:
                raise RuntimeError('unable to remove quarantine from project-local LOWTRAN: ' + removed.stderr.strip())
        signed = run(['codesign', '--force', '--sign', '-', str(target)])
        if signed.returncode:
            raise RuntimeError('ad-hoc codesign failed: ' + signed.stderr.strip())
        verified = run(['codesign', '--verify', '--verbose=2', str(target)])
        if verified.returncode:
            raise RuntimeError('new signature could not be verified: ' + verified.stderr.strip())
    except (OSError, RuntimeError) as exc:
        shutil.copy2(backup, target)
        print(f'ERROR: {exc}; restored original LOWTRAN binary', file=sys.stderr)
        return 1
    print('PASS: LOWTRAN7 has a valid local signature; startup will now retry the real scientific import.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
