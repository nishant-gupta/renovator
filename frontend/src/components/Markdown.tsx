import { Fragment, type ReactNode } from "react";

// A small, deliberately-not-exhaustive markdown renderer for the chat
// dock's assistant bubbles — headers, bold/italic/inline code, bullet and
// numbered lists, paragraphs. Builds React elements directly rather than
// an HTML string, so there's no dangerouslySetInnerHTML and therefore no
// injection surface, even though this is ultimately model-generated text.

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let i = 0;

  while ((match = pattern.exec(text))) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${i++}`;
    if (token.startsWith("**")) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

const HEADER = /^(#{1,6})\s+(.*)/;
const BULLET = /^[-*]\s+(.*)/;
const NUMBERED = /^\d+[.)]\s+(.*)/;

export function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let listItems: string[] = [];
  let listKind: "ul" | "ol" | null = null;

  function flushList() {
    if (listKind && listItems.length > 0) {
      const items = listItems;
      const key = `list-${blocks.length}`;
      blocks.push(
        listKind === "ul" ? (
          <ul key={key}>
            {items.map((item, i) => (
              <li key={i}>{renderInline(item, `${key}-${i}`)}</li>
            ))}
          </ul>
        ) : (
          <ol key={key}>
            {items.map((item, i) => (
              <li key={i}>{renderInline(item, `${key}-${i}`)}</li>
            ))}
          </ol>
        ),
      );
    }
    listItems = [];
    listKind = null;
  }

  lines.forEach((rawLine, idx) => {
    const line = rawLine.trimEnd();
    const header = HEADER.exec(line);
    const bullet = BULLET.exec(line);
    const numbered = NUMBERED.exec(line);

    if (header) {
      flushList();
      const level = Math.min(header[1].length + 2, 6); // h1/h2 read too large inside a chat bubble
      const HeaderTag = `h${level}` as "h3" | "h4" | "h5" | "h6";
      blocks.push(<HeaderTag key={idx}>{renderInline(header[2], `h-${idx}`)}</HeaderTag>);
    } else if (bullet) {
      if (listKind !== "ul") flushList();
      listKind = "ul";
      listItems.push(bullet[1]);
    } else if (numbered) {
      if (listKind !== "ol") flushList();
      listKind = "ol";
      listItems.push(numbered[1]);
    } else if (line.trim() === "") {
      flushList();
    } else {
      flushList();
      blocks.push(<p key={idx}>{renderInline(line, `p-${idx}`)}</p>);
    }
  });
  flushList();

  return <Fragment>{blocks}</Fragment>;
}
