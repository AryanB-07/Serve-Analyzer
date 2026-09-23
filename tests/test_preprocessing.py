import numpy as np
import pytest

from serve_analyzer.models import PoseSequence
from serve_analyzer.preprocessing import (
    clean,
    interpolate_gaps,
    mask_low_visibility,
    smooth_series,
    window_frames,
)

nan = np.nan


def test_short_interior_gap_is_filled_linearly():
    s = np.array([0.0, 1.0, nan, nan, nan, 5.0, 6.0])
    np.testing.assert_allclose(interpolate_gaps(s, max_gap=5), np.arange(7.0))


def test_gap_at_limit_is_filled_and_longer_gap_is_not():
    five = np.array([0.0, nan, nan, nan, nan, nan, 6.0])
    six = np.array([0.0, nan, nan, nan, nan, nan, nan, 7.0])
    assert not np.isnan(interpolate_gaps(five, max_gap=5)).any()
    assert np.isnan(interpolate_gaps(six, max_gap=5)[1:7]).all()


def test_edge_gaps_are_not_extrapolated():
    s = np.array([nan, nan, 2.0, 3.0, nan])
    out = interpolate_gaps(s, max_gap=5)
    assert np.isnan(out[[0, 1, 4]]).all()
    np.testing.assert_array_equal(out[2:4], [2.0, 3.0])


def test_interpolation_does_not_modify_input():
    s = np.array([0.0, nan, 2.0])
    interpolate_gaps(s, max_gap=5)
    assert np.isnan(s[1])


def test_mask_low_visibility_blanks_xy_only():
    lm = np.array([[[10.0, 20.0, 0.9], [30.0, 40.0, 0.2]]])
    out = mask_low_visibility(lm, threshold=0.5)
    np.testing.assert_array_equal(out[0, 0], [10.0, 20.0, 0.9])
    assert np.isnan(out[0, 1, :2]).all()
    assert out[0, 1, 2] == 0.2


@pytest.mark.parametrize("ms,fps,expected", [(150, 30, 5), (150, 25, 5), (150, 240, 37), (10, 30, 5)])
def test_window_frames_is_odd_and_long_enough(ms, fps, expected):
    assert window_frames(ms, fps, polyorder=2) == expected


def test_savgol_preserves_quadratic_exactly():
    t = np.arange(30.0)
    s = 0.5 * t**2 - 3 * t + 7
    np.testing.assert_allclose(smooth_series(s, window=7, polyorder=2), s, atol=1e-9)


def test_smoothing_reduces_noise():
    rng = np.random.default_rng(0)
    t = np.linspace(0, 1, 100)
    truth = np.sin(2 * np.pi * t)
    noisy = truth + rng.normal(0, 0.1, t.size)
    smoothed = smooth_series(noisy, window=9, polyorder=2)
    assert np.abs(smoothed - truth).mean() < 0.6 * np.abs(noisy - truth).mean()


def test_smoothing_keeps_nans_and_skips_short_segments():
    s = np.array([1.0, 2.0, 1.0, nan] + list(np.arange(10.0)))
    out = smooth_series(s, window=5, polyorder=2)
    assert np.isnan(out[3])
    np.testing.assert_array_equal(out[:3], s[:3])


def test_clean_end_to_end_on_sequence():
    frames = 20
    lm = np.zeros((frames, 33, 3))
    lm[:, :, 0] = np.arange(frames)[:, None]
    lm[:, :, 1] = 100.0
    lm[:, :, 2] = 1.0
    lm[5:8, 16, 2] = 0.1
    out = clean(PoseSequence(lm, 30.0, 640, 480), 0.5, 5, smoothing_window_ms=150)
    np.testing.assert_allclose(out.landmarks[:, 16, 0], np.arange(frames), atol=1e-9)
    assert out.landmarks.shape == lm.shape
