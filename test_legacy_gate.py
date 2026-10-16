import ast
from pathlib import Path
import unittest


class LegacyGateTests(unittest.TestCase):
    def test_unreviewed_legacy_functions_stop_before_accessing_any_credentials(self):
        root = Path('.') if Path('main.py').exists() else Path('..')
        paths = [(root / 'main.py', 'upload_to_youtube')]
        if root.name == '..':
            paths.extend((root / name, 'generate_script') for name in ('main.py', 'daily_batch_runner.py', 'turkish_upload_runner.py'))
        for path, name in paths:
            with self.subTest(path=path, name=name):
                tree = ast.parse(path.read_text(encoding='utf-8'))
                fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
                # Ignore annotations while retaining the actual function body.
                fn.returns = None
                for arg in fn.args.args + fn.args.kwonlyargs:
                    arg.annotation = None
                namespace = {}
                exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), namespace)
                args = ['test'] if name == 'generate_script' else ['video', {}, None]
                with self.assertRaisesRegex(ValueError, 'Legacy'):
                    namespace[name](*args)
