"""PDF文档解析器（支持文本版和扫描版PDF）"""
import PyPDF2
from typing import Dict, Any, List, Optional
from .base import BaseParser
import os
import logging
import re

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """PDF文档解析器（支持文本提取）"""
    
    def __init__(self):
        """初始化解析器"""
        super().__init__()
    
    def _clean_text(self, text: str) -> str:
        """
        清理文本，处理特殊字符和公式，避免乱码
        优化：保留数学公式的LaTeX格式
        
        Args:
            text: 原始文本
            
        Returns:
            清理后的文本
        """
        if not text:
            return ""
        
        # 确保是字符串类型
        if isinstance(text, bytes):
            try:
                text = text.decode('utf-8', errors='replace')
            except Exception:
                text = text.decode('latin-1', errors='replace')
        
        # 先提取并保护公式
        from utils.formula_extractor import FormulaExtractor
        text = FormulaExtractor.preserve_formulas_in_text(text)
        
        # 统一换行符
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # 移除控制字符（保留换行、制表符和常见空白字符）
        # 保留：\n (换行), \t (制表符), 空格
        # 移除：其他控制字符（0x00-0x08, 0x0B-0x0C, 0x0E-0x1F, 0x7F-0x9F）
        # 但保留公式标记内的内容
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        
        # 处理常见的数学符号和公式字符
        # 保留Unicode数学符号（U+2200到U+22FF）
        # 这些符号包括：∀, ∃, ∑, ∏, ∫, √, ∞, ≠, ≤, ≥, ∈, ∉, ⊂, ⊃, ∪, ∩, ∅, etc.
        # 不需要移除，这些是有效的数学符号
        
        # 处理常见的编码问题：替换常见的错误编码字符
        replacements = {
            '\ufffd': '',  # Unicode替换字符，通常表示编码错误
            '\u200b': '',  # 零宽空格
            '\u200c': '',  # 零宽非连字符
            '\u200d': '',  # 零宽连字符
            '\ufeff': '',  # 字节顺序标记
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        # 规范化空白字符：将多个连续空白字符替换为单个空格
        # 但保留换行符和公式标记
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # 如果行包含公式标记，特殊处理
            if '$$' in line or '$' in line:
                # 保护公式部分
                parts = re.split(r'(\$\$.*?\$\$|\$[^\$]+\$)', line)
                cleaned_parts = []
                for part in parts:
                    if part.startswith('$') and part.endswith('$'):
                        cleaned_parts.append(part)  # 保留公式
                    else:
                        cleaned_parts.append(re.sub(r'[ \t]+', ' ', part))  # 清理其他部分
                cleaned_line = ''.join(cleaned_parts)
            else:
                cleaned_line = re.sub(r'[ \t]+', ' ', line)
            cleaned_lines.append(cleaned_line)
        text = '\n'.join(cleaned_lines)
        
        # 移除行首行尾的空白（但保留公式标记）
        lines = text.split('\n')
        final_lines = []
        for line in lines:
            if '$$' in line or '$' in line:
                # 对于包含公式的行，只移除公式外的空白
                final_lines.append(line)
            else:
                final_lines.append(line.strip())
        text = '\n'.join(final_lines)
        
        return text
    
    def parse(self, file_path: str) -> Dict[str, Any]:
        """解析PDF文件（自动检测文本版或扫描版，增强版：支持图片OCR、表格提取、公式分析）"""
        text_content = []
        metadata = {}
        # 运行时开关（同步解析路径）
        try:
            from services.runtime_config import get_runtime_config_sync

            _cfg = get_runtime_config_sync()
            _modules = _cfg.get("modules") or {}
            ocr_enabled = bool(_modules.get("ocr_image_enabled", True))
            table_enabled = bool(_modules.get("table_parse_enabled", True))
        except Exception:
            ocr_enabled = True
            table_enabled = True
        
        try:
            # 首先尝试使用PyPDF2提取文本（文本版PDF）
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                # 提取元数据
                if pdf_reader.metadata:
                    metadata = {
                        "title": pdf_reader.metadata.get("/Title", ""),
                        "author": pdf_reader.metadata.get("/Author", ""),
                        "subject": pdf_reader.metadata.get("/Subject", ""),
                        "pages": len(pdf_reader.pages)
                    }
                
                # 提取文本内容
                total_pages = len(pdf_reader.pages)
                extracted_pages = 0
                
                # 增强功能：提取图片OCR文字
                image_ocr_text = ""
                if ocr_enabled:
                    try:
                        from utils.image_ocr import image_ocr
                        ocr_result = image_ocr.extract_text_from_pdf_images(file_path)
                        ocr_images = ocr_result.get("images") or []
                        if ocr_images:
                            image_ocr_parts = []
                            for image in ocr_images:
                                page_no = image.get("page")
                                image_index = image.get("image_index")
                                image_text = image.get("text", "")
                                if image_text:
                                    image_ocr_parts.append(
                                        f"[图片文字 page={page_no} image={image_index}]\n{image_text}"
                                    )
                            image_ocr_text = "\n\n".join(image_ocr_parts)
                            metadata["image_ocr"] = {
                                "image_count": ocr_result.get("image_count", 0),
                                "ocr_text_length": len(image_ocr_text),
                                "images": [
                                    {
                                        "page": image.get("page"),
                                        "image_index": image.get("image_index"),
                                        "confidence": image.get("confidence", 0.0),
                                        "line_count": image.get("line_count", 0),
                                        "text_length": len(image.get("text", "") or ""),
                                        "width": image.get("width"),
                                        "height": image.get("height"),
                                    }
                                    for image in ocr_images
                                ],
                            }
                    except Exception as e:
                        logger.warning(f"PDF图片OCR失败: {e}")
                
                for page_num, page in enumerate(pdf_reader.pages):
                    try:
                        text = page.extract_text()
                        if text and text.strip():
                            # 清理文本，处理特殊字符和公式
                            text = self._clean_text(text)
                            text_content.append({
                                "page": page_num + 1,
                                "text": text
                            })
                            extracted_pages += 1
                    except Exception as e:
                        logger.warning(f"提取第 {page_num + 1} 页文本时出错: {str(e)}")
                        continue
                
                full_text = "\n\n".join([page["text"] for page in text_content])
                
                # 合并OCR文字
                if image_ocr_text:
                    full_text += "\n\n[图片文字]\n" + image_ocr_text
                
                # 如果所有页面都没有文本，记录警告
                if not full_text.strip() and total_pages > 0:
                    logger.warning(f"PDF文件包含 {total_pages} 页，但未提取到任何文本。可能是扫描版PDF。")
                
                # 增强功能：提取表格
                tables_info = []
                if table_enabled:
                    try:
                        from utils.table_extractor import TableExtractor
                        tables = TableExtractor.extract_table_from_text(full_text)
                        for table in tables:
                            tables_info.append({
                                "type": table.get("type"),
                                "html": table.get("html"),
                                "markdown": table.get("markdown"),
                                "semantic": TableExtractor.extract_semantic_structure(table.get("data", []))
                            })
                        if tables_info:
                            metadata["tables"] = tables_info
                    except Exception as e:
                        logger.warning(f"表格提取失败: {e}")
                
                # 增强功能：分析公式
                formulas_info = []
                try:
                    from utils.formula_analyzer import FormulaAnalyzer
                    formulas_info = FormulaAnalyzer.extract_all_formulas_info(full_text)
                    if formulas_info:
                        metadata["formulas"] = formulas_info
                except Exception as e:
                    logger.warning(f"公式分析失败: {e}")
                
                return {
                    "text": full_text,
                    "metadata": {
                        **metadata,
                        "page_count": len(pdf_reader.pages),
                        "pages": text_content,
                        "extraction_method": "text_extraction",
                        "extracted_pages": extracted_pages
                    }
                }
        except Exception as e:
            raise Exception(f"Failed to parse PDF file: {e}")
    
    def supported_extensions(self) -> List[str]:
        return ["pdf"]

