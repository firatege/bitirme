"""NNLS + simplex-projection tests."""
from __future__ import annotations

import numpy as np

from services.worker.models.stacking import (
    fit_y_ens_weights,
    nnls_ridge,
    nnls_ridge_weighted,
    project_simplex,
)


def test_project_simplex_sums_to_one():
    w = np.array([0.3, 0.2, 0.8, -0.1])
    p = project_simplex(w)
    assert np.isclose(p.sum(), 1.0)
    assert (p >= 0).all()


def test_project_simplex_already_on_simplex_unchanged():
    w = np.array([0.25, 0.25, 0.25, 0.25])
    p = project_simplex(w)
    assert np.allclose(p, w)


def test_nnls_ridge_perfect_fit():
    # y = 0.6*x1 + 0.4*x2
    rng = np.random.default_rng(0)
    A = rng.random((50, 2))
    y = 0.6 * A[:, 0] + 0.4 * A[:, 1]
    w = nnls_ridge(A, y, alpha=0.0, iters=2000)
    assert np.allclose(w.sum(), 1.0)
    assert np.allclose(w, [0.6, 0.4], atol=0.05)


def test_nnls_ridge_single_column_returns_one():
    A = np.ones((10, 1))
    y = np.ones(10)
    w = nnls_ridge(A, y)
    assert w == np.array([1.0])


def test_nnls_ridge_weighted_matches_unweighted_on_unit_weights():
    rng = np.random.default_rng(0)
    A = rng.random((40, 3))
    y = rng.random(40)
    w_u = nnls_ridge(A, y)
    w_w = nnls_ridge_weighted(A, y, sample_w=np.ones(40))
    assert np.allclose(w_u, w_w, atol=1e-3)


def test_fit_y_ens_weights_prefers_better_model():
    rng = np.random.default_rng(0)
    truth = rng.normal(10, 2, 30)
    yhat_bad = truth + rng.normal(0, 5, 30)   # noisy
    yhat_good = truth + rng.normal(0, 0.5, 30) # near-perfect
    w_bad, w_good = fit_y_ens_weights(yhat_bad, yhat_good, truth)
    assert w_good > w_bad
    assert np.isclose(w_bad + w_good, 1.0)
