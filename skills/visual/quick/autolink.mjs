// Turns mentions in the page text into links, using the page's own Links box as the only source of
// URLs: an id that is not in the box stays plain text, nothing is guessed.
// Skips text inside <a>, the page and section titles (h1, h2), <svg> diagrams, <title>, <style> and <script>.

const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function rules(links) {
  const out = [];
  for (const l of links || []) {
    const num = (l.label.match(/\d{3,}/) || [])[0];
    if (l.kind === "workitem" && num) {
      // ADO 93210, AB#93210, #93210 or a bare 93210
      out.push({ src: `(?<![\\w#/.-])(?:ADO\\s+|AB#|#)?${num}(?![\\w])`, url: l.url, weight: 2 });
    } else if (l.kind === "pr" && num) {
      out.push({ src: `\\b(?:PR|pull request)\\s*#?${num}\\b`, url: l.url, weight: 3 });
    } else if (l.kind === "commit") {
      const sha = (l.label.match(/\b[0-9a-f]{7,40}\b/) || [])[0];
      // the short id, or any longer form of it (up to the full 40-char sha)
      if (sha) out.push({ src: `(?<![0-9a-f])${sha}[0-9a-f]{0,${40 - sha.length}}(?![0-9a-f])`, url: l.url, weight: 1 });
    } else if (l.kind === "branch") {
      out.push({ src: `(?<![\\w/-])${esc(l.label)}(?![\\w/-])`, url: l.url, weight: 4 + l.label.length / 1000 });
    }
  }
  // longer, more specific patterns first (a branch name contains the work item id)
  return out.sort((a, b) => b.weight - a.weight);
}

const SKIP = /^<\/?(a|h1|h2|svg|title|style|script)\b/i;   // card titles (h3) are content: linked

export function autolink(html, links) {
  const rs = rules(links);
  if (!rs.length) return html;
  const re = new RegExp(rs.map((r) => `(${r.src})`).join("|"), "gi");
  let skip = 0;
  return html.split(/(<[^>]+>)/).map((part) => {
    if (part.startsWith("<")) {
      if (SKIP.test(part) && !part.endsWith("/>")) skip += part[1] === "/" ? -1 : 1;
      return part;
    }
    if (skip > 0 || !part) return part;
    return part.replace(re, (m, ...groups) => {
      const i = groups.findIndex((g, k) => k < rs.length && g !== undefined);
      return `<a class="ref" href="${rs[i].url}" target="_blank" rel="noopener">${m}</a>`;
    });
  }).join("");
}

// Self-check: node autolink.mjs
if (process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, "/").split("/").pop())) {
  const links = [
    { kind: "workitem", label: "ADO 93210 — x", url: "W" },
    { kind: "pr", label: "PR 34449", url: "P" },
    { kind: "commit", label: "96e16cb — x", url: "C" },
    { kind: "branch", label: "dev/a/0.0.1/bug/93210-x", url: "B" },
  ];
  const t = (h) => autolink(h, links);
  const a = (u, m) => `<a class="ref" href="${u}" target="_blank" rel="noopener">${m}</a>`;
  console.assert(t("<p>Fix for ADO 93210.</p>") === `<p>Fix for ${a("W", "ADO 93210")}.</p>`, "work item");
  console.assert(t("<p>see 93210 and AB#93210</p>") === `<p>see ${a("W", "93210")} and ${a("W", "AB#93210")}</p>`, "bare + AB#");
  console.assert(t("<p>PR #34449</p>") === `<p>${a("P", "PR #34449")}</p>`, "pr");
  console.assert(t("<p>commit 96e16cb7e5d5</p>") === `<p>commit ${a("C", "96e16cb7e5d5")}</p>`, "longer sha");
  console.assert(t("<p>on dev/a/0.0.1/bug/93210-x now</p>") === `<p>on ${a("B", "dev/a/0.0.1/bug/93210-x")} now</p>`, "branch wins over id");
  console.assert(t("<h2>ADO 93210</h2>") === "<h2>ADO 93210</h2>", "no links in section titles");
  console.assert(t("<h3>Tags (ADO 93210)</h3>") === `<h3>Tags (${a("W", "ADO 93210")})</h3>`, "card titles are linked");
  console.assert(t('<svg><text>93210</text></svg>') === '<svg><text>93210</text></svg>', "no links in diagrams");
  console.assert(t("<p>port 932100 and 193210</p>") === "<p>port 932100 and 193210</p>", "no partial numbers");
  console.assert(t("<p>ADO 11111</p>") === "<p>ADO 11111</p>", "unknown id stays plain");
  console.log("ok");
}
