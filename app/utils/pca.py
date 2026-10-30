
import numpy as np


def fit(matrix,
        n_components=3):

    mean = matrix.mean(axis=0, dtype=np.float64).astype(matrix.dtype)
    centered = matrix - mean

    _, singular, vt = np.linalg.svd(centered, full_matrices=False)

    components = vt[:n_components]
    strongest = np.abs(components).argmax(axis=1)
    signs = np.sign(components[np.arange(n_components), strongest])
    components = components * signs[:, None]

    variance = singular ** 2
    explained = variance[:n_components] / variance.sum()

    return mean, components, singular[:n_components], explained


def transform(vectors, mean, components):

    return (vectors - mean) @ components.T
