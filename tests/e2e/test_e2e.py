"""Bind every scenario under ``features/``.

``scenarios()`` walks directories recursively, so one module covers every
feature file — there is no reason for one per feature. The ``@e2e`` tags that
decide what runs where are declared in the feature files themselves; see
``docs/design/testing.md``.
"""

from pytest_bdd import scenarios

scenarios("features")
