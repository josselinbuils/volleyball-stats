import numpy as np

from volleyball_stats.ball import decode


def test_decode_reads_best_cell_and_offsets():
    seq, rows, cols = 2, 27, 48
    output = np.zeros((seq * 3, rows, cols), dtype=np.float32)
    # Frame 0: ball in cell (row 10, col 20), half a cell right and a quarter down.
    output[0, 10, 20] = 0.9
    output[1, 10, 20] = 0.5
    output[2, 10, 20] = 0.25
    # Frame 1: low confidence everywhere but one cell.
    output[3, 0, 0] = 0.1

    (x0, y0, c0), (x1, y1, c1) = decode(output, seq, width=768, height=432)

    assert (x0, y0, c0) == (20.5 * 16, 10.25 * 16, np.float32(0.9))
    assert (x1, y1) == (0.0, 0.0)
    assert c1 == np.float32(0.1)
