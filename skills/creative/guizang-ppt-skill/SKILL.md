---
name: guizang-ppt-skill
description: "Use when creating single-file HTML web PPT decks with horizontal slide navigation, WebGL backgrounds, magazine-style or Swiss-style visual systems, section covers, data hero slides, image grids, or when users ask for 杂志风 PPT, 瑞士风 PPT, Swiss Style, or a horizontal swipe deck."
version: 1.0.0
author: op7418, ported by Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [web-ppt, slides, html, presentation, deck, creative, webgl, swiss-style, magazine-design]
    category: creative
    homepage: https://github.com/op7418/guizang-ppt-skill
    source_commit: f6676c3f315e4cbf8abb41daa26377688a716a5f
    related_skills: [claude-design, p5js, powerpoint, popular-web-designs]
---

# Magazine Web PPT

## Overview

Create a **single-file HTML slide deck** with horizontal navigation, WebGL background effects, keyboard/wheel/touch controls, ESC index view, Lucide icons, and Motion One entry animations.

The skill ships two complete templates:

| Style | Template | Best For | Detailed References |
|---|---|---|---|
| **A · 电子杂志 x 电子墨水** | `assets/template.html` | 人文分享、行业观察、商业发布、强杂志感演讲 | `references/layouts.md`, `references/themes.md`, `references/components.md` |
| **B · 瑞士国际主义 / Swiss Style** | `assets/template-swiss.html` | 技术产品、数据汇报、工程/设计分享、年度总结 | `references/swiss-layout-lock.md`, `references/layouts-swiss.md`, `references/themes-swiss.md` |

The output is a static `index.html` plus optional local images in an adjacent `images/` directory. It is not a `.pptx` workflow; use the `powerpoint` skill for PowerPoint files.

## When To Use

Use this skill when the user asks for:

- a web PPT, HTML slide deck, horizontal swipe deck, browser-based slides, or one-file presentation
- 杂志风 PPT, 电子杂志风, Monocle-like editorial slides, or cinematic presentation pages
- 瑞士风 PPT, Swiss Style, Helvetica/grid-based slides, data-heavy visual reports, or product/engineering decks
- section divider pages, data hero slides, large quote pages, image grids, product launch decks, or demo day decks
- a deck that can be opened directly in a browser without PowerPoint/Keynote

Do not use this skill for:

- editing or reading `.pptx` files; use `powerpoint`
- dense spreadsheet/table reporting where the page is mostly rows and columns
- collaborative presentation editing
- generic landing pages or app UIs; use `claude-design` / `popular-web-designs`

## Workflow

### 1. Clarify Before Building

If the user already provided a complete outline and assets, proceed with reasonable assumptions. Otherwise ask only the highest-impact missing questions, usually 1-3 at a time.

Must resolve before writing HTML:

| Question | Why It Matters |
|---|---|
| Style A or B? | Chooses the template, layout reference, and theme file. |
| Audience and setting? | Controls tone, detail level, and slide density. |
| Talk duration? | Rough page count: 15 min ~= 10 pages, 30 min ~= 20 pages, 45 min ~= 25-30 pages. |
| Source material? | Existing docs, data, articles, URLs, screenshots, or old slides should drive content. |
| Images? | Determines image folder, filenames, ratios, and which layouts are viable. |
| Theme color? | Style A has 5 presets; Style B has 4 accent presets. |
| Hard constraints? | Required claims/data or forbidden topics prevent rework. |

Codex note: ask in normal chat. Do not use Claude Code-specific `ask_question` mechanisms.

### 2. Choose The Style

Default recommendations:

| Signal | Recommended Style |
|---|---|
| "杂志感", "人文", "Monocle", narrative, cultural, editorial, documentary images | **A · 电子杂志** |
| "瑞士风", "Swiss Style", "Helvetica", "极简", "网格", KPI, product/engineering/data report | **B · 瑞士国际主义** |
| Many KPI numbers, roadmap, systems, process, proof blocks | **B** |
| Many human/documentary photos or essay-like story flow | **A** |

Do not mix Style A and Style B in one deck. Their class names and visual assumptions overlap but are not interchangeable.

### 3. Create The Deck Folder

Copy the selected template to the target deck directory and create an image folder:

```bash
mkdir -p "project/ppt/images"

# Style A
cp "<SKILL_ROOT>/assets/template.html" "project/ppt/index.html"

# Style B
cp "<SKILL_ROOT>/assets/template-swiss.html" "project/ppt/index.html"
```

Immediately replace the `<title>` placeholder and later confirm:

```bash
grep -n "\\[必填\\]" "project/ppt/index.html"
```

For image assets, use names like `01-cover.jpg`, `03-dashboard.png`, `08-system-map.jpg`. Keep images beside `index.html` under `images/`.

### 4. Load The Right References

Read only the reference files needed for the chosen style:

| Need | Read |
|---|---|
| Style A theme colors | `references/themes.md` |
| Style A slide skeletons | `references/layouts.md` |
| Style A components | `references/components.md` |
| Style B hard layout constraints | `references/swiss-layout-lock.md` first |
| Style B theme colors | `references/themes-swiss.md` |
| Style B registered layouts | `references/layouts-swiss.md` |
| Image generation prompts and ratios | `references/image-prompts.md` |
| Final QA checklist | `references/checklist.md` |

For Style B, `references/swiss-layout-lock.md` is mandatory. It constrains body pages to registered `S01-S22` layouts, with explicit `data-layout="Sxx"` on each body slide.

### 5. Fill Slides From Layout Skeletons

Do not write slide structures from scratch.

For Style A, choose from the 10 editorial layout families in `references/layouts.md`: cover, section divider, data hero, quote+image, image grid, pipeline, question page, big quote, before/after, lead image + side text.

For Style B, choose registered `S01-S22` layouts from `references/layouts-swiss.md`. Respect these hard rules:

- every body slide has `data-layout="Sxx"`
- no unregistered body structures unless the user explicitly requests experimental layouts
- top Chinese titles default to the left/top content axis, not centered
- SVG is for geometry only; visible text labels belong in HTML
- S22 hero images use the `21:9` slot and `data-image-slot="s22-hero-21x9"`

Before inserting layout code, inspect the selected template's `<style>` block and confirm the classes you plan to use exist there. If a class is missing, either choose a supported layout or add the reusable class to the template stylesheet once. Avoid per-slide ad hoc styling for repeated patterns.

### 6. Theme And Rhythm

Pick one theme preset and use it for the whole deck.

Style A presets live in `references/themes.md`:

- 墨水经典
- 靛蓝瓷
- 森林墨
- 牛皮纸
- 沙丘

Style B presets live in `references/themes-swiss.md`:

- IKB / 克莱因蓝
- lemon yellow
- lemon green
- safety orange

Plan the slide rhythm before coding:

- each section must include one of `light`, `dark`, `hero light`, `hero dark`, or the Style B equivalent such as `accent` / `split` where the template requires it
- avoid more than 3 consecutive pages with the same visual mode
- decks longer than 8 pages need at least one strong opener and one strong visual reset
- insert hero/section/question pages every 3-4 content-heavy pages

### 7. Preview And Validate

Open the generated HTML in a browser and verify real rendering, not just source code.

```bash
open "project/ppt/index.html"
```

Required checks:

- title placeholder replaced
- every page fits at 16:9 without clipped text
- no blank first frame
- navigation works with arrow keys, wheel, touch, and ESC index
- images load from `images/` and are not distorted
- text hierarchy matches the selected style
- no obvious overlap with navigation dots or footer

For Style B, also run:

```bash
node "<SKILL_ROOT>/scripts/validate-swiss-deck.mjs" "project/ppt/index.html"
```

Then read `references/checklist.md` and apply the style-specific QA section before handing off.

## Image Rules

Tell the user the expected asset convention before implementation:

- folder: `ppt/images/` beside `index.html`
- filenames: `{page}-{semantic-name}.{ext}`, for example `01-cover.jpg`
- photos/screenshots: JPG or PNG, ideally >= 1600px wide
- image-heavy decks should keep total image size reasonable for smooth page turns
- if filenames change, update all `images/...` references in HTML

If running in Codex and the draft would benefit from generated visuals, ask before generating images. Match the chosen style: editorial/ink for Style A, Swiss/grid/accent for Style B. Keep generated image text in the deck language.

## Common Pitfalls

1. **Mixing templates and layouts.** Style A layout classes are not valid Style B recipes, and vice versa.
2. **Leaving placeholders.** Always grep for `[必填]` before delivery.
3. **Inventing Swiss pages.** In Style B, use `S01-S22` unless the user explicitly asks for experimental pages.
4. **Skipping browser preview.** Source code can look plausible while the deck clips or overlaps.
5. **Overusing custom colors.** Use preset themes only; arbitrary hex colors usually break the system.
6. **Letting images decide layout.** Choose the slide slot and ratio first, then crop/regenerate images to fit.
7. **Putting visible labels inside Swiss SVGs.** Use HTML labels/captions instead.

## Verification Checklist

- [ ] Correct template copied to the target `index.html`
- [ ] `images/` directory exists if the deck uses images
- [ ] `<title>` and all `[必填]` placeholders are replaced
- [ ] Theme preset selected from the correct reference file
- [ ] Slide rhythm planned and visible in `class="slide ..."` values
- [ ] Style A pages use only Style A layouts/classes
- [ ] Style B pages use registered `data-layout="Sxx"` body layouts
- [ ] Browser preview checked on the target viewport
- [ ] Style B validator passes when applicable
- [ ] `references/checklist.md` final QA reviewed
