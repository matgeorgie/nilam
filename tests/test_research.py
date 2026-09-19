import pandas as pd

from kerala_land_lab.research import grouped_stratified_split


def test_grouped_split_has_no_leakage_and_represents_every_class():
    rows = []
    for target in range(3):
        for group in range(6):
            rows.extend(
                {"target": target, "source_polygon_id": f"{target}-{group}"}
                for _ in range(group + 1)
            )
    frame = pd.DataFrame(rows)
    splits = grouped_stratified_split(frame, seed=7)
    groups = [set(frame.iloc[index].source_polygon_id) for index in splits]
    assert not groups[0] & groups[1]
    assert not groups[0] & groups[2]
    assert not groups[1] & groups[2]
    assert all(set(frame.iloc[index].target) == {0, 1, 2} for index in splits)
