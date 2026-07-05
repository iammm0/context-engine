import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from parsers.word_parser import _build_word_image_ocr_metadata


def test_build_word_image_ocr_metadata_tracks_embedded_image_sources():
    metadata = _build_word_image_ocr_metadata(
        [
            {
                "image_index": 1,
                "target": "media/image1.png",
                "ocr_text": "图中包含召回率",
                "confidence": 0.91,
                "line_count": 2,
                "width": 640,
                "height": 320,
            },
            {
                "image_index": 2,
                "target": "media/image2.png",
                "ocr_text": "",
                "confidence": 0.0,
                "line_count": 0,
            },
        ]
    )

    assert metadata["image_count"] == 2
    assert metadata["ocr_text_length"] == len("图中包含召回率")
    assert metadata["images"][0]["image_index"] == 1
    assert metadata["images"][0]["target"] == "media/image1.png"
    assert metadata["images"][0]["text_length"] == len("图中包含召回率")
    assert metadata["images"][1]["text_length"] == 0
