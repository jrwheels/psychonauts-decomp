#!/usr/bin/env python3
"""Read-only publication guard. Findings show locations/rules, never matching text.

Default: inspect staged blobs, including force-added ignored files. Other modes
inspect candidate worktree paths, a Git tree, or every snapshot in a history range.
This heuristic complements human review; it cannot establish ownership or legality.
"""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

MAX_BYTES = 1024 * 1024
PRIVATE_PARTS = {'.local', '.venv', 'venv', 'build', 'backup', 'decomp', 'mod', '__pycache__',
                 'wineprefix', 'node_modules', 'session-logs'}
DENIED_SUFFIXES = {'.exe','.dll','.obj','.o','.lib','.pdb','.so','.dylib','.iso','.msi','.cab',
    '.zip','.7z','.tar','.gz','.xz','.zst','.pkg','.ppf','.lpf','.lub','.glb','.gltf','.fbx',
    '.blend','.fbmod','.fbproject','.dds','.png','.jpg','.jpeg','.sqlite','.db','.dmp','.log',
    '.pyc','.asm','.jsonl','.bundle','.plb','.jan','.apf','.pba','.tga','.zpkg'}
# Assemble marker fragments so this checker and its synthetic tests can be scanned.
PERSONAL = re.compile(rb'(?:/' + rb'(?:home|Users|run/media)/[^\s/"\'<>]+|[A-Za-z]:[\\/]Users[\\/][^\s\\/"\'<>]+)')
SECRETS = [re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE' + rb' KEY-----'),
    re.compile(rb'\b(?:gh' + rb'p_|github_' + rb'pat_)[A-Za-z0-9_]{20,}'),
    re.compile(rb'\bAK' + rb'IA[A-Z0-9]{16}\b'),
    re.compile(rb'\bxox' + rb'[baprs]-[A-Za-z0-9-]{20,}'),
    re.compile(rb'\bsk' + rb'-(?:proj-)?[A-Za-z0-9_-]{30,}'),
    re.compile(rb'(?i)\b(?:api_key|access_token|client_secret|password)\s*[:=]\s*["\'][A-Za-z0-9/+_=\-]{20,}["\']')]


def inspect(path, data, mode='100644', max_bytes=MAX_BYTES):
    """Return rule names only; callers must not expose matching contents."""
    rules=[];p=PurePosixPath(path);parts={x.lower() for x in p.parts};name=p.name.lower()
    if p.is_absolute() or '..' in p.parts or '\\' in path:
        rules.append('unsafe_path')
    if parts & PRIVATE_PARTS or any(x.lower().startswith('.env') and x.lower() != '.env.example' for x in p.parts):
        rules.append('private_or_generated_path')
    if p.suffix.lower() in DENIED_SUFFIXES or name in {'cl.exe','mspdb80.dll','msobj80.dll','toolchain.json','reference.json'}:
        rules.append('binary_compiler_or_generated_artifact')
    if any('reskate' in x for x in parts) or name.startswith('studio_'):
        rules.append('excluded_modding_workstream')
    if name == 'export_chat_log.py' or any(x in name for x in ('chat-session','chat-transcript','resume-state','pause-state','session-state')):
        rules.append('private_session_record')
    if mode == '120000':rules.append('symlink_requires_review')
    if len(data)>max_bytes:rules.append('oversized_artifact')
    if data.startswith((b'MZ',b'\x7fELF',b'PK\x03\x04',b'MSCF',b'\x1f\x8b')) or b'\0' in data:
        rules.append('binary_or_archive_content')
    if PERSONAL.search(data):rules.append('absolute_personal_path')
    if any(pattern.search(data) for pattern in SECRETS):rules.append('credential_marker')
    if ((b'"type": "response_' + b'item"') in data or
            (b'"session_' + b'id"' in data and b'"role": "user"' in data)):
        rules.append('transcript_content')
    return sorted(set(rules))


def git(root, *args):
    return subprocess.check_output(['git','-C',str(root),*args], stderr=subprocess.PIPE)


def safe_candidate(root, name):
    p=PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name:
        raise ValueError('candidate list must contain repository-relative file paths')
    path=root/name
    if any(x.is_symlink() for x in [path,*path.parents] if x != root and x.is_relative_to(root)):
        raise ValueError('candidate symlinks require manual review: '+name)
    if not path.is_file():raise ValueError('candidate is not a file: '+name)
    return path


def tree_entries(root, ref):
    for item in git(root,'ls-tree','-rz','--full-tree',ref).split(b'\0'):
        if not item:continue
        meta,path=item.split(b'\t',1);mode,kind,oid=meta.decode().split()
        yield path.decode(),oid,mode,kind


def scan(root, kind, value=None):
    findings=[];checked=0;cache={}
    def blob(name,oid,mode='100644'):
        nonlocal checked
        checked+=1
        if oid not in cache:cache[oid]=git(root,'cat-file','blob',oid)
        for rule in inspect(name,cache[oid],mode):findings.append(dict(path=name,rule=rule,object=oid))
    if kind in ('tree','history'):
        refs=[value] if kind=='tree' else git(root,'rev-list',value).decode().splitlines()
        seen=set()
        for ref in refs:
            if kind=='history':
                commit=git(root,'cat-file','commit',ref)
                for rule in inspect('commit-message',commit):
                    findings.append(dict(path='commit:'+ref,rule=rule))
            for name,oid,mode,entry_kind in tree_entries(root,ref):
                if (name,oid,mode) in seen:continue
                seen.add((name,oid,mode))
                if entry_kind!='blob':
                    findings.append(dict(path=name,rule='submodule_requires_review'));continue
                blob(name,oid,mode)
    elif kind=='staged':
        for item in git(root,'ls-files','--stage','-z').split(b'\0'):
            if not item:continue
            meta,name=item.split(b'\t',1);mode,oid,stage=meta.decode().split()
            if stage!='0':
                findings.append(dict(path=name.decode(),rule='unmerged_index'));continue
            if mode=='160000':
                findings.append(dict(path=name.decode(),rule='submodule_requires_review'));continue
            blob(name.decode(),oid,mode)
    else:
        names=(Path(value).read_text().splitlines() if kind=='paths' else
               git(root,'ls-files','--cached','--others','--exclude-standard','-z').decode().split('\0'))
        for name in sorted(set(names)):
            if not name or name.startswith('#'):continue
            if kind=='worktree' and not (root/name).exists():continue
            path=safe_candidate(root,name);checked+=1
            for rule in inspect(name,path.read_bytes()):findings.append(dict(path=name,rule=rule))
    return dict(schema_version=1,scope=kind,files_checked=checked,findings=findings,success=not findings)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    group=ap.add_mutually_exclusive_group()
    group.add_argument('--staged',action='store_true',help='entire index, default')
    group.add_argument('--worktree',action='store_true',help='tracked plus nonignored untracked files')
    group.add_argument('--tree',metavar='REF',help='complete snapshot')
    group.add_argument('--history',metavar='REV_RANGE',help='every snapshot and commit in range')
    group.add_argument('--paths-from',type=Path,help='explicit candidate paths, one per line')
    args=ap.parse_args()
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],text=True).strip())
    kind,value=('tree',args.tree) if args.tree else ('history',args.history) if args.history else ('paths',args.paths_from) if args.paths_from else ('worktree',None) if args.worktree else ('staged',None)
    try:result=scan(root,kind,value)
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        print(json.dumps(dict(success=False,error=type(exc).__name__,
                              message='Scan failed; check relative file paths and Git refs.')));return 2
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1


if __name__=='__main__':
    sys.exit(main())
