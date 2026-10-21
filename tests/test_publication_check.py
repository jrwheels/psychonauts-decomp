"""Publication checks inspect Git blobs, including deleted history and forced files."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from publication_check import inspect, scan, safe_candidate


class PublicationTests(unittest.TestCase):
    def test_secret_and_path_findings_do_not_expose_values(self):
        token='gh'+'p_'+'X'*36
        path='/'+'home'+'/synthetic-owner/project'
        rules=inspect('docs/example.md',(token+' '+path).encode())
        self.assertIn('credential_marker',rules);self.assertIn('absolute_personal_path',rules)
        self.assertNotIn(token,str(rules));self.assertNotIn(path,str(rules))
        windows='C:'+chr(92)+'Users'+chr(92)+'synthetic-owner'
        self.assertIn('absolute_personal_path',inspect('x.md',windows.encode()))

    def test_proprietary_generated_transcript_and_oversized_content(self):
        for name,data,rule in [('.local/VC/include/header.h',b'text','private_or_generated_path'),
            ('renamed.txt',b'MZ'+bytes(10),'binary_or_archive_content'),
            ('tools/input.dll',b'text','binary_compiler_or_generated_artifact'),
            ('docs/chat-session.log',b'text','private_session_record'),
            ('x.md',b'12345','oversized_artifact')]:
            self.assertIn(rule,inspect(name,data,max_bytes=4))
        self.assertIn('transcript_content',inspect('x.txt',b'{"type": "response_'+b'item"}'))
        self.assertIn('symlink_requires_review',inspect('link',b'destination','120000'))

    def test_original_assets_and_excluded_workstream_are_blocked(self):
        for name in ('reference/model.plb','reference/clip.jan','reference/animation.apf'):
            self.assertIn('binary_compiler_or_generated_artifact',inspect(name,b'fixture'))
        for name in ('third_party/reskate-research/example.cpp','tools/studio_example.py'):
            self.assertIn('excluded_modding_workstream',inspect(name,b'fixture'))
        self.assertIn('private_session_record',inspect('tools/export_chat_log.py',b'fixture'))

    def test_normal_source_and_placeholders_are_allowed(self):
        self.assertEqual(inspect('src/game/example.cpp',b'int f() { return 1; }'),[])
        self.assertEqual(inspect('docs/setup.md',b'$REFERENCE /path/to/owned/reference $VC'),[])

    def repo(self,d):
        root=Path(d)
        subprocess.run(['git','init','-q',str(root)],check=True)
        return root

    def command(self,root,*args):
        return subprocess.check_output(['git','-C',str(root),*args])

    def commit(self,root):
        self.command(root,'-c','user.name=Synthetic','-c','user.email=synthetic@example.invalid','commit','-qm','Synthetic fixture')

    def test_staged_reads_index_and_catches_force_added_ignored_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.repo(d);p=root/'file.txt';p.write_text('gh'+'p_'+'Z'*36)
            self.command(root,'add','file.txt');p.write_text('clean working copy')
            self.assertFalse(scan(root,'staged')['success'])
            self.assertTrue(scan(root,'worktree')['success'])
            (root/'.gitignore').write_text('.local/\n');(root/'.local').mkdir();(root/'.local/cl.exe').write_bytes(b'MZ')
            self.command(root,'add','-f','.local/cl.exe')
            self.assertIn('private_or_generated_path',{x['rule'] for x in scan(root,'staged')['findings']})

    def test_history_catches_removed_file_and_reused_blob_under_private_name(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.repo(d);(root/'safe.txt').write_text('fixture');self.command(root,'add','.');self.commit(root)
            (root/'chat-session.log').write_text('fixture');self.command(root,'add','.');self.commit(root)
            self.command(root,'rm','chat-session.log');self.commit(root)
            self.assertTrue(scan(root,'tree','HEAD')['success'])
            self.assertFalse(scan(root,'history','HEAD')['success'])

    def test_explicit_paths_reject_traversal_and_symlinks(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'safe').write_text('fixture');(root/'link').symlink_to(root/'safe')
            for name in ('../outside','/absolute','link'):
                with self.assertRaises(ValueError):safe_candidate(root,name)
