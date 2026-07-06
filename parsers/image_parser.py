"""单图 OCR 解析器 - 使用 PaddleOCR 提取图片中的文字"""
from typing import Dict, Any, List
from .base import BaseParser
import os
import logging

logger = logging.getLogger(__name__)


class ImageParser(BaseParser):
    """单张图片解析器（支持 jpg/png/bmp/webp/tiff 等，通过 OCR 提取文字）"""

    def parse(self, file_path: str) -> Dict[str, Any]:
        """解析图片文件：OCR 提取文字作为正文，置信度等写入 metadata。"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"图片文件不存在: {file_path}")
        # 运行时开关：可关闭 OCR（低配模式）
        try:
            from services.runtime_config import get_runtime_config_sync

            cfg = get_runtime_config_sync()
            modules = cfg.get("modules") or {}
            if not bool(modules.get("ocr_image_enabled", True)):
                return {
                    "text": "",
                    "metadata": {
                        "extraction_method": "image_ocr",
                        "error": "OCR 已关闭（运行时配置）",
                        "confidence": 0.0,
                    },
                }
        except Exception:
            pass
        try:
            from utils.image_ocr import image_ocr
            ocr_result = image_ocr.extract_text_from_image(file_path)
        except Exception as e:
            logger.warning(f"图片 OCR 失败: {file_path}, 错误: {e}")
            return {
                "text": "",
                "metadata": {
                    "extraction_method": "image_ocr",
                    "error": str(e),
                    "confidence": 0.0,
                },
            }
        text = ocr_result.get("text", "") or ""
        metadata = {
            "extraction_method": "image_ocr",
            "confidence": ocr_result.get("confidence", 0.0),
            "line_count": ocr_result.get("line_count", 0),
            "image_ocr": {
                "image_count": 1 if text else 0,
                "ocr_text_length": len(text),
                "images": [
                    {
                        "image_index": 1,
                        "confidence": ocr_result.get("confidence", 0.0),
                        "line_count": ocr_result.get("line_count", 0),
                        "text_length": len(text),
                        "bbox": ocr_result.get("bbox"),
                    }
                ] if text else [],
            },
        }
        if ocr_result.get("error"):
            metadata["error"] = ocr_result["error"]
        if ocr_result.get("boxes"):
            metadata["boxes"] = ocr_result["boxes"]
        if ocr_result.get("bbox"):
            metadata["bbox"] = ocr_result["bbox"]
        return {"text": text, "metadata": metadata}

    def supported_extensions(self) -> List[str]:
        return ["jpg", "jpeg", "png", "bmp", "webp", "tiff", "tif"]
