import React, { useMemo } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { Copy, Check } from 'lucide-react';

interface MarkdownRendererProps {
  content: string;
  className?: string;
  accentColor?: string;
}

// Configure marked with sensible GitHub Flavored Markdown defaults
marked.setOptions({
  gfm: true,
  breaks: true,
});

/**
 * Preprocesses raw text from LLMs:
 * 1. Converts triple single quotes (''') to triple backticks (```)
 * 2. Cleans up formatting quirks
 */
function preprocessMarkdown(raw: string): string {
  if (!raw) return '';

  // Replace triple single-quotes '''lang or ''' with ```lang or ```
  let text = raw.replace(/'''([a-zA-Z0-9_-]*)/g, '```$1');

  return text;
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  className = '',
  accentColor,
}) => {
  const renderedHtml = useMemo(() => {
    const cleaned = preprocessMarkdown(content);
    const rawHtml = marked.parse(cleaned) as string;
    return DOMPurify.sanitize(rawHtml, {
      ADD_ATTR: ['target', 'rel'],
    });
  }, [content]);

  return (
    <div
      className={`markdown-content prose-invert max-w-none text-slate-200 text-sm leading-relaxed ${className}`}
      dangerouslySetInnerHTML={{ __html: renderedHtml }}
    />
  );
};
