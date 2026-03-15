try:
    from .validator import validate_full
except ImportError:
    from validator import validate_full
print("Success")
