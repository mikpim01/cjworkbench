from collections import namedtuple
import pandas as pd
from cjwkernel.types import I18nMessage


UsedColumn = namedtuple("UsedColumn", ("type", "tab_name"))


def render(table, params, *, tab_name, input_columns):
    if not params["tabs"]:
        return table

    # Find conflicting columns. Columns are complementary if they have the same
    # type; they conflict if they have different types. Iterate through all
    # tabs, checking the (colname, type, tab_name) trios.
    used_columns = {}
    for colname in table.columns:
        column = input_columns[colname]
        used_columns[colname] = UsedColumn(column.type, tab_name)

    for tab in params["tabs"]:
        for column in tab.columns.values():
            colname = column.name
            if column.name in used_columns:
                used_column = used_columns[column.name]
                if used_column.type != column.type:
                    return I18nMessage.trans(
                        "staticmodules.concattabs.badParam.tabs.differentTypes.message",
                        default='Cannot concatenate column "{column_name}" of type '
                        '"{column_type}" in "{column_tab_name}" to column '
                        '"{used_column_name}" of type "{used_column_type}" in '
                        '"{used_column_tab_name}". Please convert one or the '
                        "other so they are the same type.",
                        args={
                            "column_name": column.name,
                            "column_type": column.type,
                            "column_tab_name": tab.name,
                            "used_column_name": column.name,  # They are equal
                            "used_column_type": used_column.type,
                            "used_column_tab_name": used_column.tab_name,
                        },
                    )
            else:
                used_columns[column.name] = UsedColumn(column.type, tab.name)

    if params["add_source_column"]:
        source_colname = params["source_column_name"] or "Source"
        if source_colname in used_columns:
            tab_name = used_columns[source_colname].tab_name
            return I18nMessage.trans(
                "staticmodules.concattabs.badParam.add_source_column.alreadyExists",
                default='Cannot create column "{source_colname}": "{tab_name}" '
                "already has that column. Please write a different Source "
                "column name.",
                args={"source_colname": source_colname, "tab_name": tab_name},
            )
    else:
        source_colname = None

    to_join = {tab_name: table}
    for tab in params["tabs"]:
        to_join[tab.name] = tab.dataframe

    # second 'names' value must be anything that _isn't_ source_colname. Our
    # hack: 'xxx' + source_colname.
    concatenated = pd.concat(to_join, sort=False, ignore_index=True)

    if source_colname:
        # Add 'source' column as a Categorical. This takes virtually no
        # disk+RAM, as opposed to a str column which can take a lot.
        source_categories = []  # list of tab names
        source_values = []  # list of source_categories indexes
        if len(table):
            source_categories.append(tab_name)
            source_values.extend([0] * len(table))
        for tab in params["tabs"]:
            if len(tab.dataframe):
                source_values.extend([len(source_categories)] * len(tab.dataframe))
                source_categories.append(tab.name)
        sources = pd.Categorical.from_codes(source_values, source_categories)
        concatenated.insert(loc=0, column=source_colname, value=sources)

    return concatenated
