"""图片OCR工具 - 使用PaddleOCR提取图片中的文字"""
from typing import Dict, Any, List, Optional, Tuple
from utils.logger import logger
import os


def _clean_coord(value: float) -> int | float:
    rounded = round(float(value), 2)
    return int(rounded) if rounded.is_integer() else rounded


def _bbox_from_boxes(boxes: List[Any]) -> Optional[List[int | float]]:
    """Merge OCR line boxes into one compact [x1, y1, x2, y2] bbox."""
    xs: List[float] = []
    ys: List[float] = []

    def add_point(x_value: Any, y_value: Any) -> None:
        if isinstance(x_value, (int, float)) and isinstance(y_value, (int, float)):
            xs.append(float(x_value))
            ys.append(float(y_value))

    for box in boxes or []:
        if isinstance(box, dict):
            left = box.get("left", box.get("x1", box.get("x")))
            top = box.get("top", box.get("y1", box.get("y")))
            right = box.get("right", box.get("x2"))
            bottom = box.get("bottom", box.get("y2"))
            width = box.get("width", box.get("w"))
            height = box.get("height", box.get("h"))
            if right is None and isinstance(left, (int, float)) and isinstance(width, (int, float)):
                right = float(left) + float(width)
            if bottom is None and isinstance(top, (int, float)) and isinstance(height, (int, float)):
                bottom = float(top) + float(height)
            add_point(left, top)
            add_point(right, bottom)
            continue

        if not isinstance(box, (list, tuple)):
            continue
        if len(box) == 4 and all(isinstance(value, (int, float)) for value in box):
            add_point(box[0], box[1])
            add_point(box[2], box[3])
            continue
        for point in box:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                add_point(point[0], point[1])

    if not xs or not ys:
        return None
    return [_clean_coord(min(xs)), _clean_coord(min(ys)), _clean_coord(max(xs)), _clean_coord(max(ys))]


class ImageOCR:
    """图片OCR工具类"""
    
    def __init__(self):
        """初始化OCR工具"""
        self._ocr_engine = None
        self._initialized = False
    
    def _initialize_ocr(self):
        """延迟初始化PaddleOCR"""
        if self._initialized:
            return
        
        try:
            from paddleocr import PaddleOCR
            # 初始化OCR引擎，支持中英文
            self._ocr_engine = PaddleOCR(
                use_angle_cls=True,  # 使用角度分类器
                lang='ch',  # 中文
                use_gpu=False,  # 根据环境自动选择
                show_log=False  # 不显示日志
            )
            self._initialized = True
            logger.info("PaddleOCR 初始化成功")
        except ImportError:
            logger.warning("PaddleOCR 未安装，无法使用OCR功能")
            self._ocr_engine = None
        except Exception as e:
            logger.error(f"初始化 PaddleOCR 失败: {e}", exc_info=True)
            self._ocr_engine = None
    
    def extract_text_from_image(self, image_path: str) -> Dict[str, Any]:
        """
        从图片中提取文字
        
        Args:
            image_path: 图片文件路径
        
        Returns:
            包含提取文本和元数据的字典：
            - text: 提取的文本内容
            - confidence: 置信度
            - boxes: 文字框位置信息
        """
        if not self._initialized:
            self._initialize_ocr()
        
        if not self._ocr_engine:
            return {
                "text": "",
                "confidence": 0.0,
                "boxes": [],
                "error": "OCR引擎未初始化"
            }
        
        if not os.path.exists(image_path):
            return {
                "text": "",
                "confidence": 0.0,
                "boxes": [],
                "error": f"图片文件不存在: {image_path}"
            }
        
        try:
            # 使用PaddleOCR识别图片
            result = self._ocr_engine.ocr(image_path, cls=True)
            
            if not result or not result[0]:
                return {
                    "text": "",
                    "confidence": 0.0,
                    "boxes": [],
                    "error": "未识别到文字"
                }
            
            # 提取文本和置信度
            text_parts = []
            boxes = []
            confidences = []
            lines = []
            
            for line in result[0]:
                if len(line) >= 2:
                    box_info = line[0]  # 文字框坐标
                    text_info = line[1]  # (文字内容, 置信度)
                    
                    if isinstance(text_info, tuple) and len(text_info) >= 2:
                        text_content = text_info[0]
                        confidence = text_info[1]
                        
                        text_parts.append(text_content)
                        boxes.append(box_info)
                        confidences.append(confidence)
                        lines.append({
                            "text": text_content,
                            "confidence": confidence,
                            "box": box_info,
                        })
            
            # 合并文本
            full_text = "\n".join(text_parts)
            
            # 计算平均置信度
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            logger.info(f"OCR识别完成 - 图片: {image_path}, 文字行数: {len(text_parts)}, 平均置信度: {avg_confidence:.2f}")
            
            return {
                "text": full_text,
                "confidence": avg_confidence,
                "boxes": boxes,
                "bbox": _bbox_from_boxes(boxes),
                "line_count": len(text_parts),
                "lines": lines,
            }
        
        except Exception as e:
            logger.error(f"OCR识别失败: {image_path}, 错误: {e}", exc_info=True)
            return {
                "text": "",
                "confidence": 0.0,
                "boxes": [],
                "error": str(e)
            }
    
    def extract_text_from_pdf_images(self, pdf_path: str) -> Dict[str, Any]:
        """
        从PDF中提取图片并进行OCR识别
        
        Args:
            pdf_path: PDF文件路径
        
        Returns:
            包含每页图片OCR结果的字典
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF 未安装，无法提取PDF中的图片")
            return {
                "images": [],
                "total_text": "",
                "error": "PyMuPDF未安装"
            }
        
        if not self._initialized:
            self._initialize_ocr()
        
        if not self._ocr_engine:
            return {
                "images": [],
                "total_text": "",
                "error": "OCR引擎未初始化"
            }
        
        try:
            doc = fitz.open(pdf_path)
            all_images = []
            all_text = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                # 获取页面中的图片
                image_list = page.get_images(full=True)
                
                for img_index, img in enumerate(image_list):
                    try:
                        # 提取图片
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        
                        # 保存临时图片文件
                        import tempfile
                        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{image_ext}") as tmp_file:
                            tmp_file.write(image_bytes)
                            tmp_image_path = tmp_file.name
                        
                        # OCR识别
                        ocr_result = self.extract_text_from_image(tmp_image_path)
                        
                        # 清理临时文件
                        try:
                            os.unlink(tmp_image_path)
                        except Exception:
                            pass
                        
                        if ocr_result.get("text"):
                            all_images.append({
                                "page": page_num + 1,
                                "image_index": img_index + 1,
                                "xref": xref,
                                "extension": image_ext,
                                "width": base_image.get("width"),
                                "height": base_image.get("height"),
                                "text": ocr_result.get("text", ""),
                                "confidence": ocr_result.get("confidence", 0.0),
                                "bbox": ocr_result.get("bbox"),
                                "line_count": ocr_result.get("line_count", 0),
                                "lines": ocr_result.get("lines", []),
                            })
                            all_text.append(ocr_result.get("text", ""))
                    
                    except Exception as e:
                        logger.warning(f"提取PDF第{page_num+1}页第{img_index+1}张图片失败: {e}")
                        continue
            
            doc.close()
            
            total_text = "\n\n".join(all_text)
            
            logger.info(f"PDF图片OCR完成 - PDF: {pdf_path}, 图片数: {len(all_images)}, 总文字长度: {len(total_text)}")
            
            return {
                "images": all_images,
                "total_text": total_text,
                "image_count": len(all_images)
            }
        
        except Exception as e:
            logger.error(f"PDF图片OCR失败: {pdf_path}, 错误: {e}", exc_info=True)
            return {
                "images": [],
                "total_text": "",
                "error": str(e)
            }


# 全局OCR实例
image_ocr = ImageOCR()

