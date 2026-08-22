from src.eval.compare import values_match

def test_compare_voltage():
    assert values_match("120 V", "120", "voltage") is True

def test_compare_categorical_lov():
    lov = {"synonyms": {"undermount": "Built-in"}}
    assert values_match("undermount", "Built-in", "mount_type", lov) is True

def test_compare_compound_dimension():
    # 1. Equivalent mixed-fraction dimensions
    assert values_match("33 3/8 in H x 23 3/4 in W", "33.375 H x 23.75 W", "dimensions") is True
    # 2. Equivalent hyphen-fraction dimensions
    assert values_match("24-1/4 in", "24.25 in", "dimensions") is True
    # 3. Different dimensions -> no match
    assert values_match("24-1/4 in", "25 in", "dimensions") is False
    # 4. Labeled H/W/D dimensions compared correctly (order independent)
    assert values_match("34 H x 23.8125 W x 22.562 D", "34 in H x 23 13/16 in W x 22 9/16 in D", "dimensions") is True
    assert values_match("23.8125 W x 34 H x 22.562 D", "34 in H x 23 13/16 in W x 22 9/16 in D", "dimensions") is True
    
def test_compare_unparseable():
    # It should return "unparseable_compound" if it can't parse
    assert values_match("W39.5 x D38.5 x H99.5 cm (15.6 x 15.2 x 39.2 inches)", "34 in H", "dimensions") == "unparseable_compound"
