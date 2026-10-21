# brand — the SpesNet look for sdd:visual pages

A copy of what the **SpesNet Design System** gives us, plus the glue that puts it on a page.

| File | What |
| --- | --- |
| `tokens.css` | The design system's token files, copied as they are: type, colours (light, `.dim`, `.dark`), spacing, radius, elevation, motion |
| `aliases.css` | The names sdd:visual pages use (`--bg`, `--surface`, `--accent`, `--positive` …) mapped onto those tokens |
| `public-sans-latin.woff2` | Public Sans, latin subset, variable weight 100–900 |
| `brand.mjs` | `brandTokens()`, `brandFont()` and `inject` |

## Use

- Quick mode: `quick/render.mjs` calls it. Nothing to do.
- Full mode: the page's `<style>` carries `/* @brand:font */` and `/* @brand:tokens */`. Then run

```bash
node <plugin root>/skills/visual/brand/brand.mjs inject <page.html>
```

  The markers become the inlined font and the tokens. The dark theme turns on with the OS dark
  setting. `data-theme="light" | "dim" | "dark"` on `<html>` pins a theme. A page with no marker
  gets both at the top of its first `<style>`. A page that was injected is left as it is.

## Update from the design system

The source is the **SpesNet Design System** artifact on claude.ai (project path `project/`).

1. Re-copy `tokens/typography.css`, `colors.css`, `spacing.css`, `radius.css`, `elevation.css` and
   `motion.css` into `tokens.css`, in that order, under the same header comment.
2. If the font changed, replace `public-sans-latin.woff2` (`assets/fonts/public-sans-latin.woff2`
   in the design system).
3. If a token name changed, fix `aliases.css`. Nothing else names the design system's tokens.
4. Render a sample page in light and dark and look at it.

Keep in mind:

- `--surface` in the design system is a page tint. `aliases.css` points it at `--panel` (a card),
  because that is what sdd:visual pages mean by it.
- `--warning` in the design system is a pale gold surface tint. Pages use `--caution` for the solid
  amber and its tint.
- The design system has no vector logo and no slide kit. Do not add a logo to a page.
