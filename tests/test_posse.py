"""
Setting up scaffolding for posse testing
"""

# import pytest
from posse.posse import hello 

def test_alive():
    assert hello() == "Hello world!"