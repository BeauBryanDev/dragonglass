
import numpy as np
import pytest

from app.utils.pca import fit, transform


@pytest.fixture
def matrix():

    rng = np.random.default_rng(0)
    scales = np.array([9.0, 5.0, 3.0, 1.0, 0.5, 0.2])

    return rng.normal(size=(400, 6)) * scales + 7.0


def test_components_are_orthonormal(matrix):

    _, components, _, _ = fit(matrix)

    assert components @ components.T == pytest.approx(np.eye(3))


def test_explained_variance_matches_covariance_eigenvalues(matrix):

    _, _, _, explained = fit(matrix)
    eigenvalues = np.sort(np.linalg.eigvalsh(np.cov(matrix.T)))[::-1]

    assert explained == pytest.approx(eigenvalues[:3] / eigenvalues.sum())


def test_scores_are_centered_and_ordered_by_variance(matrix):

    mean, components, _, _ = fit(matrix)
    scores = transform(matrix, mean, components)
    variances = scores.var(axis=0)

    assert scores.mean(axis=0) == pytest.approx(np.zeros(3), abs=1e-9)
    assert variances[0] > variances[1] > variances[2]


def test_a_single_vector_lands_on_its_row(matrix):

    mean, components, _, _ = fit(matrix)

    assert transform(matrix[17], mean, components) == pytest.approx(
        transform(matrix, mean, components)[17])


def test_signs_are_stable_when_data_is_reordered(matrix):

    _, first, _, _ = fit(matrix)
    _, second, _, _ = fit(matrix[::-1])

    assert first == pytest.approx(second)


def test_input_is_not_modified(matrix):

    before = matrix.copy()
    fit(matrix)

    assert np.array_equal(matrix, before)
