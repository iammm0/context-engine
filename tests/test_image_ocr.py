import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from utils.image_ocr import _bbox_from_boxes


def test_bbox_from_boxes_merges_ocr_line_polygons():
    bbox = _bbox_from_boxes(
        [
            [[10.2, 20.1], [80.8, 20.1], [80.8, 42.9], [10.2, 42.9]],
            [[15, 55], [120, 55], [120, 88], [15, 88]],
        ]
    )

    assert bbox == [10.2, 20.1, 120, 88]


def test_bbox_from_boxes_supports_rect_dicts():
    bbox = _bbox_from_boxes(
        [
            {"x": 10, "y": 20, "width": 40, "height": 30},
            {"left": 4, "top": 6, "right": 90, "bottom": 70},
        ]
    )

    assert bbox == [4, 6, 90, 70]
