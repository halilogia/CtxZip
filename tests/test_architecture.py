import ast
from pathlib import Path
import unittest


class ArchitectureTests(unittest.TestCase):
    def test_core_dependencies_are_acyclic_and_never_import_cli(self):
        root = Path(__file__).resolve().parents[1] / 'ctxzip_core'
        graph = {}
        for path in root.glob('*.py'):
            dependencies = set()
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotEqual(alias.name.split('.')[0], 'ctxzip')
                        if alias.name.startswith('ctxzip_core.'):
                            dependencies.add(alias.name.split('.')[1])
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotEqual((node.module or '').split('.')[0], 'ctxzip')
                    if node.level and node.module:
                        dependencies.add(node.module.split('.')[0])
                    elif node.module == 'ctxzip_core':
                        dependencies.update(a.name for a in node.names)
                    elif (node.module or '').startswith('ctxzip_core.'):
                        dependencies.add(node.module.split('.')[1])
            graph[path.stem] = dependencies

        def visit(name, active):
            self.assertNotIn(name, active, f'Import cycle: {active} -> {name}')
            for dependency in graph.get(name, set()):
                visit(dependency, active + [name])

        for name in graph:
            visit(name, [])
