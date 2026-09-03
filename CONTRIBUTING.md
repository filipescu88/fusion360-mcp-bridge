# Contributing

Pull requests are welcome.

## Generator contract

```python
def generate(params: dict[str, str]) -> str:
    ...
```

Returned Fusion script:

```python
def run(_context: str):
    ...
```

For large sketches:
- use `sketch.isComputeDeferred = True`,
- always restore it to `False`,
- prefer chaining actual `SketchPoint` objects,
- do not swallow Fusion API exceptions.

Run before submitting:

```bash
python -m unittest discover -s tests -v
```
