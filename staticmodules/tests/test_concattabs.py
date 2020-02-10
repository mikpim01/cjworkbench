import unittest
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from cjwkernel.pandas.types import RenderColumn, TabOutput
from staticmodules.concattabs import render
from cjwkernel.types import I18nMessage


class ConcattabsTest(unittest.TestCase):
    def test_happy_path(self):
        result = render(
            pd.DataFrame({"A": [1, 2]}),
            params={
                "tabs": [
                    TabOutput(
                        "tab-2",
                        "Tab 2",
                        {"A": RenderColumn("A", "number", "{}")},
                        pd.DataFrame({"A": [3, 4]}),
                    )
                ],
                "add_source_column": False,
                "source_column_name": "",
            },
            tab_name="Tab 1",
            input_columns={"A": RenderColumn("A", "number", "{}")},
        )
        assert_frame_equal(result, pd.DataFrame({"A": [1, 2, 3, 4]}))

    def test_error_different_types(self):
        result = render(
            pd.DataFrame({"A": ["x", "y"]}),
            params={
                "tabs": [
                    TabOutput(
                        "tab-2",
                        "Tab 2",
                        {"A": RenderColumn("A", "number", "{}")},
                        pd.DataFrame({"A": [3, 4]}),
                    )
                ],
                "add_source_column": False,
                "source_column_name": "",
            },
            tab_name="Tab 1",
            input_columns={"A": RenderColumn("A", "text", None)},
        )
        self.assertEqual(
            result,
            I18nMessage(
                "staticmodules.concattabs.badParam.tabs.differentTypes.message",
                {
                    "column_name": "A",
                    "column_type": "number",
                    "column_tab_name": "Tab 2",
                    "used_column_name": "A",
                    "used_column_type": "text",
                    "used_column_tab_name": "Tab 1",
                },
            ),
        )

    def test_allow_different_columns(self):
        result = render(
            pd.DataFrame({"A": [1, 2]}),
            params={
                "tabs": [
                    TabOutput(
                        "tab-2",
                        "Tab 2",
                        {"B": RenderColumn("B", "number", "{}")},
                        pd.DataFrame({"B": [3, 4]}),
                    )
                ],
                "add_source_column": False,
                "source_column_name": "",
            },
            tab_name="Tab 1",
            input_columns={"A": RenderColumn("A", "number", "{}")},
        )
        # This tests the ordering of columns, too
        assert_frame_equal(
            result,
            pd.DataFrame({"A": [1, 2, np.nan, np.nan], "B": [np.nan, np.nan, 3, 4]}),
        )

    def test_add_source_column(self):
        result = render(
            pd.DataFrame({"A": [1, 2]}),
            params={
                "tabs": [
                    TabOutput(
                        "tab-2",
                        "Tab 2",
                        {"A": RenderColumn("A", "number", "{}")},
                        pd.DataFrame({"A": [3, 4]}),
                    )
                ],
                "add_source_column": True,
                "source_column_name": "S",
            },
            tab_name="Tab 1",
            input_columns={"A": RenderColumn("A", "number", "{}")},
        )
        expected = pd.DataFrame(
            {
                # Source column comes _first_
                "S": ["Tab 1", "Tab 1", "Tab 2", "Tab 2"],
                "A": [1, 2, 3, 4],
            }
        )
        # Source column should be categorical: no need to load it with useless
        # copied bytes.
        expected["S"] = expected["S"].astype("category")
        assert_frame_equal(result, expected)

    def test_coerce_numbers(self):
        result = render(
            pd.DataFrame({"A": [1, 2]}),
            params={
                "tabs": [
                    TabOutput(
                        "tab-2",
                        "Tab 2",
                        {"A": RenderColumn("A", "number", "{}")},
                        pd.DataFrame({"A": [3.3, 4.4]}),
                    )
                ],
                "add_source_column": False,
                "source_column_name": "",
            },
            tab_name="Tab 1",
            input_columns={"A": RenderColumn("A", "number", "{}")},
        )
        assert_frame_equal(result, pd.DataFrame({"A": [1.0, 2.0, 3.3, 4.4]}))

    def test_coerce_categories_and_str(self):
        result = render(
            pd.DataFrame({"A": ["a", "b"]}, dtype="category"),  # cat
            params={
                "tabs": [
                    TabOutput(
                        "tab-2",
                        "Tab 2",
                        {"A": RenderColumn("A", "text", None)},
                        pd.DataFrame({"A": ["c", "d"]}),
                    )  # str
                ],
                "add_source_column": False,
                "source_column_name": "",
            },
            tab_name="Tab 1",
            input_columns={"A": RenderColumn("A", "text", None)},
        )
        assert_frame_equal(result, pd.DataFrame({"A": ["a", "b", "c", "d"]}))  # str
