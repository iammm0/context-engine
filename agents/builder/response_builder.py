"""响应构建器 - 生成HTML格式的响应"""
from typing import Dict, Any, List, Optional
from utils.logger import logger
import html


class ResponseBuilder:
    """响应构建器 - 将Agent结果组织成HTML格式"""
    
    def build_html_response(
        self,
        agent_results: List[Dict[str, Any]],
        query: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建HTML格式的响应
        
        Args:
            agent_results: Agent结果列表
            query: 用户问题
            metadata: 元数据
        
        Returns:
            HTML格式的响应字符串
        """
        html_parts = []
        
        # HTML头部和样式
        html_parts.append(self._get_html_header())
        
        # 标题部分
        html_parts.append(f'<div class="deep-research-header">')
        html_parts.append(f'<h1>深度研究结果</h1>')
        html_parts.append(f'<p class="query">问题：{html.escape(query)}</p>')
        html_parts.append(f'</div>')
        
        # Agent结果部分
        for result in agent_results:
            if result.get("error"):
                continue
            
            agent_type = result.get("agent_type", "unknown")
            content = result.get("content", "")
            sources = result.get("sources", [])
            confidence = result.get("confidence", 0.5)
            
            # Agent结果卡片
            html_parts.append(f'<div class="agent-result-card" data-agent="{agent_type}">')
            html_parts.append(f'<div class="agent-header">')
            html_parts.append(f'<h2>{self._get_agent_title(agent_type)}</h2>')
            html_parts.append(f'<span class="confidence">置信度: {confidence:.0%}</span>')
            html_parts.append(f'</div>')
            
            # 内容部分
            html_parts.append(f'<div class="agent-content">')
            # 将Markdown转换为HTML（简化处理）
            html_content = self._markdown_to_html(content)
            html_parts.append(html_content)
            html_parts.append(f'</div>')
            
            # 来源部分
            if sources:
                html_parts.append(f'<div class="agent-sources">')
                html_parts.append(f'<h3>来源：</h3>')
                html_parts.append(f'<ul>')
                for source in sources[:5]:  # 限制显示数量
                    source_title = source.get("document_title") or source.get("title") or "未知来源"
                    evidence_id = source.get("evidence_id")
                    prefix = f"[{evidence_id}] " if evidence_id else ""
                    html_parts.append(f'<li>{html.escape(prefix + source_title)}</li>')
                html_parts.append(f'</ul>')
                html_parts.append(f'</div>')
            
            html_parts.append(f'</div>')
        
        # HTML尾部
        html_parts.append(self._get_html_footer())
        
        return "\n".join(html_parts)
    
    def _get_agent_title(self, agent_type: str) -> str:
        """获取Agent的中文标题"""
        titles = {
            "document_retrieval": "📚 文档检索",
            "formula_analysis": "📐 公式分析",
            "code_analysis": "💻 代码分析",
            "concept_explanation": "💡 概念解释",
            "example_generation": "📝 示例生成",
            "summary": "📋 总结",
            "exercise": "✏️ 习题",
            "scientific_coding": "🛠️ 实现方案",
            "critic": "🧭 批判性分析",
            "argument_analysis": "🧩 论证分析",
        }
        return titles.get(agent_type, agent_type)
    
    def _markdown_to_html(self, markdown: str) -> str:
        """
        将Markdown转换为HTML（简化实现）
        
        注意：这是一个简化实现，实际应该使用专业的Markdown库
        """
        import re
        
        # 转义HTML特殊字符
        html_text = html.escape(markdown)
        
        # 标题
        html_text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html_text, flags=re.MULTILINE)
        html_text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html_text, flags=re.MULTILINE)
        html_text = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html_text, flags=re.MULTILINE)
        
        # 代码块
        html_text = re.sub(
            r'```(\w+)?\n(.*?)```',
            r'<pre><code class="language-\1">\2</code></pre>',
            html_text,
            flags=re.DOTALL
        )
        
        # 行内代码
        html_text = re.sub(r'`([^`]+)`', r'<code>\1</code>', html_text)
        
        # 公式（LaTeX）
        html_text = re.sub(r'\$\$(.*?)\$\$', r'<div class="formula-block">\1</div>', html_text, flags=re.DOTALL)
        html_text = re.sub(r'\$([^\$]+)\$', r'<span class="formula-inline">\1</span>', html_text)
        
        # 列表
        html_text = re.sub(r'^\* (.*?)$', r'<li>\1</li>', html_text, flags=re.MULTILINE)
        html_text = re.sub(r'(<li>.*?</li>)', r'<ul>\1</ul>', html_text, flags=re.DOTALL)
        
        # 段落
        paragraphs = html_text.split('\n\n')
        html_paragraphs = []
        for para in paragraphs:
            para = para.strip()
            if para and not para.startswith('<'):
                html_paragraphs.append(f'<p>{para}</p>')
            else:
                html_paragraphs.append(para)
        
        return '\n'.join(html_paragraphs)
    
    def _get_html_header(self) -> str:
        """获取HTML头部和样式"""
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>深度研究结果</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .deep-research-header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .deep-research-header h1 {
            margin: 0 0 10px 0;
            color: #2c3e50;
        }
        .query {
            color: #666;
            font-size: 16px;
            margin: 0;
        }
        .agent-result-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .agent-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e0e0e0;
        }
        .agent-header h2 {
            margin: 0;
            color: #2c3e50;
        }
        .confidence {
            background: #e3f2fd;
            color: #1976d2;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 14px;
        }
        .agent-content {
            margin: 15px 0;
        }
        .agent-content h1, .agent-content h2, .agent-content h3 {
            color: #2c3e50;
            margin-top: 20px;
            margin-bottom: 10px;
        }
        .agent-content p {
            margin: 10px 0;
        }
        .agent-content code {
            background: #f5f5f5;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 14px;
        }
        .agent-content pre {
            background: #f5f5f5;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            border-left: 4px solid #2196f3;
        }
        .agent-content pre code {
            background: none;
            padding: 0;
        }
        .formula-block {
            background: #f9f9f9;
            padding: 15px;
            margin: 15px 0;
            border-radius: 5px;
            text-align: center;
            font-family: 'Times New Roman', serif;
            border-left: 4px solid #4caf50;
        }
        .formula-inline {
            font-family: 'Times New Roman', serif;
            background: #f0f0f0;
            padding: 2px 6px;
            border-radius: 3px;
        }
        .agent-sources {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #e0e0e0;
        }
        .agent-sources h3 {
            font-size: 14px;
            color: #666;
            margin: 0 0 10px 0;
        }
        .agent-sources ul {
            margin: 0;
            padding-left: 20px;
            color: #666;
        }
        .agent-sources li {
            margin: 5px 0;
        }
    </style>
</head>
<body>"""
    
    def _get_html_footer(self) -> str:
        """获取HTML尾部"""
        return """</body>
</html>"""
