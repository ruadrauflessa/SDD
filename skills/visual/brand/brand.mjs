#!/usr/bin/env node
// SpesNet Design System for sdd:visual pages: tokens, themes and the Public Sans font.
//   brandTokens()  tokens + aliases + the dark-mode media rule      (about 14 KB of CSS)
//   brandFont()    the Public Sans @font-face with the font inlined  (about 36 KB, base64)
//   node brand.mjs inject <page.html>   fills the markers a full-mode page carries
//     /* @brand:tokens */   in a <style> block: replaced with brandTokens()
//     /* @brand:font */     in a <style> block: replaced with brandFont()
//   A page with no marker gets both at the top of its first <style>.
import { readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const brandDir = dirname(fileURLToPath(import.meta.url));
export const TOKENS_MARKER = "/* @brand:tokens */";
export const FONT_MARKER = "/* @brand:font */";

// Light is the base. The OS dark setting turns on the design system's dark theme unless the page
// pins a theme with data-theme (light | dim | dark); a .dim or .dark class works too.
export async function brandTokens() {
  const tokens = await readFile(join(brandDir, "tokens.css"), "utf8");
  const aliases = await readFile(join(brandDir, "aliases.css"), "utf8");
  const dark = tokens.match(/\n\.dark \{([\s\S]*?)\n\}/);
  if (!dark) throw new Error("brand/tokens.css has no .dark block");
  const themed = tokens
    .replace("\n.dark {", '\n.dark, :root[data-theme="dark"] {')
    .replace("\n.dim {", '\n.dim, :root[data-theme="dim"] {');
  const auto = `@media (prefers-color-scheme: dark) {\n  :root:not([data-theme]):not(.dim):not(.light) {${dark[1]}\n  }\n}`;
  return `:root { color-scheme: light; }\n${themed}\n${auto}\n${aliases}`;
}

export async function brandFont() {
  const data = (await readFile(join(brandDir, "public-sans-latin.woff2"))).toString("base64");
  return `@font-face {\n  font-family: 'Public Sans';\n  font-style: normal;\n  font-weight: 100 900;\n  font-display: swap;\n  src: url("data:font/woff2;base64,${data}") format('woff2');\n  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;\n}`;
}

export async function injectBrand(html) {
  if (html.includes("tokens/typography.css")) return html; // already injected
  const tokens = await brandTokens();
  const font = await brandFont();
  const hasTokens = html.includes(TOKENS_MARKER);
  const hasFont = html.includes(FONT_MARKER);
  if (!hasTokens && !hasFont) {
    if (!/<style[^>]*>/i.test(html)) throw new Error("The page has no <style> block to put the brand in.");
    return html.replace(/<style[^>]*>/i, (open) => `${open}\n${font}\n${tokens}\n`);
  }
  // A replacer function, so a "$" in the CSS is never read as a replacement pattern.
  return html.replace(TOKENS_MARKER, () => tokens).replace(FONT_MARKER, () => font);
}

async function main() {
  const [command, file] = process.argv.slice(2);
  if (command !== "inject" || !file) throw new Error("Usage: node brand.mjs inject <page.html>");
  const html = await readFile(file, "utf8");
  await writeFile(file, await injectBrand(html), "utf8");
  process.stdout.write(`${file}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
