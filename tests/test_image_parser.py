import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from parsers.image_parser import ImageParser


def test_image_parser_preserves_ocr_bbox(monkeypatch, tmp_path):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake image bytes")

    import services.runtime_config as runtime_config
    import utils.image_ocr as image_ocr_module

    monkeypatch.setattr(
        runtime_config,
        "get_runtime_config_sync",
        lambda: {"modules": {"ocr_image_enabled": True}},
    )
    monkeypatch.setattr(
        image_ocr_module.image_ocr,
        "extract_text_from_image",
        lambda _path: {
            "text": "图中包含召回率 0.92",
            "confidence": 0.88,
            "line_count": 2,
            "boxes": [[[10, 20], [300, 20], [300, 180], [10, 180]]],
            "bbox": [10, 20, 300, 180],
        },
    )

    result = ImageParser().parse(str(image_path))

    image_ref = result["metadata"]["image_ocr"]["images"][0]
    assert image_ref["bbox"] == [10, 20, 300, 180]
    assert result["metadata"]["bbox"] == [10, 20, 300, 180]
