import six
from solver import add


def test_offline_dependency_and_addition() -> None:
    assert six.__version__ == "1.17.0"
    assert add(2, 3) == 5
