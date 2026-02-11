import textwrap

from linescore.parsers.python import PythonParser


def make_source(code: str) -> str:
    return textwrap.dedent(code).strip()


class TestPythonParser:
    def setup_method(self):
        self.parser = PythonParser()

    def test_extracts_top_level_functions(self):
        source = make_source("""
            def foo():
                x = 1
                return x

            def bar():
                y = 2
                return y
        """)
        functions = self.parser.extract_functions(source)
        names = [f.name for f in functions]
        assert "foo" in names
        assert "bar" in names

    def test_extracts_class_methods_with_prefix(self):
        source = make_source("""
            class MyClass:
                def my_method(self):
                    x = compute()
                    return x
        """)
        functions = self.parser.extract_functions(source)
        assert len(functions) == 1
        assert functions[0].name == "MyClass.my_method"

    def test_skips_empty_functions(self):
        source = make_source("""
            def empty():
                pass

            def not_empty():
                x = 1
                return x
        """)
        functions = self.parser.extract_functions(source)
        names = [f.name for f in functions]
        assert "empty" not in names
        assert "not_empty" in names

    def test_filters_trivial_statements(self):
        source = make_source("""
            def foo(self):
                self.x = x
                return
                return None
        """)
        functions = self.parser.extract_functions(source)
        # All statements are trivial, so the function should be skipped
        assert len(functions) == 0

    def test_keeps_nontrivial_statements(self):
        source = make_source("""
            def process():
                result = compute_value(data)
                filtered = [x for x in result if x > 0]
                return filtered
        """)
        functions = self.parser.extract_functions(source)
        assert len(functions) == 1
        stmts = functions[0].statements
        assert any("compute_value" in s for s in stmts)
        assert any("filtered" in s for s in stmts)

    def test_compound_statement_header_extracted(self):
        source = make_source("""
            def check(value):
                if value > 10:
                    result = "big"
                    return result
        """)
        functions = self.parser.extract_functions(source)
        assert len(functions) == 1
        stmts = functions[0].statements
        assert any("if value > 10" in s for s in stmts)

    def test_skips_imports_inside_functions(self):
        source = make_source("""
            def foo():
                import os
                path = os.getcwd()
                return path
        """)
        functions = self.parser.extract_functions(source)
        assert len(functions) == 1
        stmts = functions[0].statements
        assert not any("import" in s for s in stmts)
        assert any("os.getcwd()" in s for s in stmts)

    def test_skips_nested_function_defs(self):
        source = make_source("""
            def outer():
                x = 1

                def inner():
                    y = 2
                    return y

                return x
        """)
        functions = self.parser.extract_functions(source)
        outer_funcs = [f for f in functions if f.name == "outer"]
        assert len(outer_funcs) == 1
        # outer's statements should not include inner's body
        stmts = outer_funcs[0].statements
        assert any("x = 1" in s for s in stmts)
        assert not any("y = 2" in s for s in stmts)

    def test_multiple_classes(self):
        source = make_source("""
            class A:
                def method_a(self):
                    a = compute_a()
                    return a

            class B:
                def method_b(self):
                    b = compute_b()
                    return b
        """)
        functions = self.parser.extract_functions(source)
        names = [f.name for f in functions]
        assert "A.method_a" in names
        assert "B.method_b" in names

    def test_needs_at_least_some_statements(self):
        source = make_source("""
            def only_pass():
                pass
        """)
        functions = self.parser.extract_functions(source)
        assert len(functions) == 0

    def test_async_function(self):
        source = make_source("""
            async def fetch_data():
                response = await client.get(url)
                return response
        """)
        functions = self.parser.extract_functions(source)
        assert len(functions) == 1
        assert functions[0].name == "fetch_data"
