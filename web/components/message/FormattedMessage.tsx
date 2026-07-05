"use client";

import MarkdownRenderer from "./MarkdownRenderer";

interface FormattedMessageProps {
  content: string;
  className?: string;
  citationIds?: string[];
  activeCitationId?: string | null;
  onCitationClick?: (citationId: string) => void;
}

/**
 * 格式化消息主组件
 * 职责：整合调用子组件，进行简单的格式预处理
 * - 将 $$...$$ 块级公式转换为 ```math 代码块格式（便于 MarkdownRenderer 处理）
 * - 保持 $...$ 行内公式格式不变（MathJax 会自动识别）
 * - 委托给 MarkdownRenderer 进行实际渲染
 */
/**
 * 检测内容是否是HTML格式
 */
function isHTML(content: string): boolean {
  if (!content || typeof content !== "string") return false;
  const trimmed = content.trim();
  return (
    trimmed.startsWith("<!DOCTYPE") ||
    trimmed.startsWith("<html") ||
    (trimmed.startsWith("<div") && trimmed.includes("</div>")) ||
    (trimmed.includes("<") && trimmed.includes(">") && /<[a-z][\s\S]*>/i.test(trimmed) && trimmed.split("<").length > 3)
  );
}

/**
 * 从HTML中提取文本内容（简单版本）
 */
function htmlToMarkdown(html: string): string {
  if (typeof window === "undefined") {
    // 服务端：简单处理，移除HTML标签
    return html
      .replace(/<!DOCTYPE[\s\S]*?>/gi, "")
      .replace(/<html[\s\S]*?>/gi, "")
      .replace(/<\/html>/gi, "")
      .replace(/<head>[\s\S]*?<\/head>/gi, "")
      .replace(/<body[\s\S]*?>/gi, "")
      .replace(/<\/body>/gi, "")
      .replace(/<h([1-6])>([\s\S]*?)<\/h\1>/gi, (_, level, text) => {
        return `${"#".repeat(parseInt(level, 10))} ${text.trim()}\n\n`;
      })
      .replace(/<p>([\s\S]*?)<\/p>/gi, "$1\n\n")
      .replace(/<div[\s\S]*?>/gi, "\n")
      .replace(/<\/div>/gi, "\n")
      .replace(/<pre>([\s\S]*?)<\/pre>/gi, (_, code) => {
        return `\n\`\`\`\n${code.trim()}\n\`\`\`\n\n`;
      })
      .replace(/<code>([\s\S]*?)<\/code>/gi, "`$1`")
      .replace(/<strong>([\s\S]*?)<\/strong>/gi, "**$1**")
      .replace(/<em>([\s\S]*?)<\/em>/gi, "*$1*")
      .replace(/<a[\s\S]*?href=["']([^"']+)["'][\s\S]*?>([\s\S]*?)<\/a>/gi, "[$2]($1)")
      .replace(/<[^>]+>/g, "")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  // 客户端：使用DOM API提取文本
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    
    // 移除script和style标签
    const scripts = doc.querySelectorAll("script, style");
    scripts.forEach((el) => {
      el.remove();
    });
    
    // 提取body内容
    const body = doc.body || doc.documentElement;
    if (!body) return html;
    
    // 简单的HTML到Markdown转换
    let markdown = body.innerText || body.textContent || "";
    
    // 尝试保留一些结构
    const headings = body.querySelectorAll("h1, h2, h3, h4, h5, h6");
    headings.forEach((heading) => {
      const level = parseInt(heading.tagName.charAt(1), 10);
      const text = heading.textContent || "";
      markdown = markdown.replace(text, `${"#".repeat(level)} ${text}\n\n`);
    });
    
    // 处理代码块
    const codeBlocks = body.querySelectorAll("pre code, pre");
    codeBlocks.forEach((code) => {
      const codeText = code.textContent || "";
      const language = code.className.match(/language-(\w+)/)?.[1] || "";
      markdown = markdown.replace(
        codeText,
        `\n\`\`\`${language}\n${codeText}\n\`\`\`\n\n`
      );
    });
    
    return markdown.trim() || html;
  } catch (error) {
    console.warn("HTML转换失败，返回原始内容:", error);
    return html;
  }
}

export default function FormattedMessage({
  content,
  className = "",
  citationIds = [],
  activeCitationId,
  onCitationClick,
}: FormattedMessageProps) {
  // 处理空内容
  if (!content || typeof content !== "string") {
    return <div className={`${className} text-gray-900 dark:text-gray-100`}>内容为空</div>;
  }

  // 检测并处理HTML内容
  let processedContent = content;
  if (isHTML(content)) {
    processedContent = htmlToMarkdown(content);
  }

  // 简单的预处理：将 $$...$$ 块级公式转换为 ```math 代码块格式
  // 这样 MarkdownRenderer 可以统一处理
  const preprocessContent = (text: string): string => {
    let processed = text;

    // 首先标记所有已存在的代码块，避免误处理
    const codeBlockPlaceholders: string[] = [];
    const codeBlockPattern = /```[\s\S]*?```/g;
    processed = processed.replace(codeBlockPattern, (match) => {
      const placeholder = `__CODE_BLOCK_${codeBlockPlaceholders.length}__`;
      codeBlockPlaceholders.push(match);
      return placeholder;
    });

    // 将 $$...$$ 块级公式转换为 ```math 代码块
    // 这样 MarkdownRenderer 的 code 组件可以识别并委托给 FormulaRenderer
    processed = processed.replace(
      /\$\$([\s\S]*?)\$\$/g,
      (match, formula) => {
        if (match.includes('__CODE_BLOCK_')) return match;
        const cleanFormula = formula.trim();
        return `\n\n\`\`\`math\n${cleanFormula}\n\`\`\`\n\n`;
      }
    );

    // 将 \[...\] 块级公式也转换为 ```math 代码块
    processed = processed.replace(
      /\\\[([\s\S]*?)\\\]/g,
      (match, formula) => {
        if (match.includes('__CODE_BLOCK_')) return match;
        const cleanFormula = formula.trim();
        return `\n\n\`\`\`math\n${cleanFormula}\n\`\`\`\n\n`;
      }
    );

    // 恢复所有代码块占位符
    codeBlockPlaceholders.forEach((codeBlock, index) => {
      processed = processed.replace(`__CODE_BLOCK_${index}__`, codeBlock);
    });

    return processed;
  };

  const finalContent = preprocessContent(processedContent);

  return (
    <div className={`physics-content ${className}`}>
      <style jsx>{`
        .physics-content {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
            'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;
          line-height: 1.8;
        }
        
        /* 响应式布局 */
        @media (max-width: 640px) {
          .physics-content {
            font-size: 0.9em;
            line-height: 1.7;
          }
        }
        
        @media (min-width: 641px) and (max-width: 768px) {
          .physics-content {
            font-size: 0.95em;
          }
        }
        
        /* MathJax 样式优化 */
        .physics-content :global(.MathJax) {
          font-size: 1.1em;
        }
        
        @media (max-width: 640px) {
          .physics-content :global(.MathJax) {
            font-size: 1em;
          }
        }
        
        .physics-content :global(.MathJax_Display) {
          margin: 1em auto;
          padding: 0.75em 1em;
          background: #f8f9fa;
          border-radius: 6px;
          border-left: 3px solid #3b82f6;
          overflow-x: auto;
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
          display: block;
          text-align: center;
          -webkit-overflow-scrolling: touch;
        }
        
        @media (max-width: 640px) {
          .physics-content :global(.MathJax_Display) {
            margin: 0.75em auto;
            padding: 0.5em 0.75em;
            border-radius: 4px;
            border-left-width: 2px;
          }
        }
        
        @media (prefers-color-scheme: dark) {
          .physics-content :global(.MathJax_Display) {
            background: #1f2937;
            border-left-color: #60a5fa;
          }
        }
        
        /* 行内公式样式 */
        .physics-content :global(.MathJax:not(.MathJax_Display)) {
          background: #f1f5f9;
          padding: 0.15em 0.4em;
          border-radius: 4px;
          margin: 0 0.2em;
          font-size: 1.05em;
        }
        
        @media (max-width: 640px) {
          .physics-content :global(.MathJax:not(.MathJax_Display)) {
            padding: 0.1em 0.3em;
            margin: 0 0.15em;
            font-size: 0.95em;
          }
        }
        
        @media (prefers-color-scheme: dark) {
          .physics-content :global(.MathJax:not(.MathJax_Display)) {
            background: #374151;
          }
        }
      `}</style>
      <MarkdownRenderer
        content={finalContent}
        citationIds={citationIds}
        activeCitationId={activeCitationId}
        onCitationClick={onCitationClick}
      />
    </div>
  );
}
