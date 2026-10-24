# Help authoring and viewer contract

The canonical end-user guide is [help/README.md](../planner-main/docs/help/README.md), with a table of
contents and a short quickstart. Each topic links back to that page.
Editing, Export and Shortcuts are maintained here without root-level duplicates.
Setup, implementation details, asset specifications and porting instructions belong
in [Development](DEVELOPMENT.md), the resource READMEs or [parity](parity/README.md).

## Portable Markdown

Edit the help pages only when the user explicitly requests it.

Use the common subset of CommonMark: ATX headings, paragraphs, emphasis, inline
code, ordered/unordered lists, ordinary relative links and fenced code blocks
when needed. Conventional pipe tables and relative image links are also supported;
use a Markdown renderer with pipe-table support in a future port. Avoid raw HTML,
Qt-specific markup, task lists, directives,
wiki links, automatic bare-URL links and renderer-specific heading anchors.
Link to another Markdown page instead of relying on generated heading IDs.
For a hard line break within a paragraph, end the source line with a single
backslash. The viewer keeps the following line in that paragraph without adding
paragraph spacing. Escaped backslashes and code examples retain their literal
contents. This is a rendering correction around Qt's native importer, with source
files left intact. See `checks/check_help_line_breaks.py`.
Do not put source launch commands, installation instructions or local machine
paths in end-user pages. Write for someone already using the app.

Use inline code for keypresses, shortcuts and mouse gestures, such as `Ctrl + S`
and `Right-click`. Use bold for named UI controls, panels, menu commands and
options, such as **Object Properties** and **File > Save Project**. Keep surrounding
instructions outside the shortcut's code span. Inline code has horizontal
padding in the viewer; that padding is presentation only and is omitted when
copying text. Keep source Markdown free of padding characters or custom markup.

Use UTF-8. Keep one level-one title at the beginning of each page. Link labels
must describe the destination. Keep user pages inside `docs/help`, and use
relative `.md` links. Image paths use forward slashes, with files bundled inside
the help folder. Do not make Help depend on an Internet connection.

## Desktop viewer and future web parity

- Help > Help and F1 open the landing page; Keyboard shortcuts opens its page
  in the same reusable window.
  Reopening a minimized help window maximizes and focuses it.
- The window is modeless, resizable, minimizable, maximizable and independently closable. Opening it does
  not change selection, project contents, dirty state or either undo history.
- Home opens the landing page. Back and Forward restore visited pages and scroll
  positions. Their enabled states reflect available history.
  Navigation uses 24 px icons in 32 px buttons, with tooltips and accessible names.
  Home uses `home.svg`. Back and Forward use `handle_up.svg` rotated left and right.
  Mouse Back/Forward buttons, dedicated navigation keys and platform Back/Forward
  shortcuts navigate the same history throughout the Help window.
  Closing Help clears navigation history; reopening begins with only the requested
  page. Minimizing preserves the current navigation session.
- Links navigate on activation, not hover. Text is selectable and copyable.
  Enter does not activate a default navigation button. Escape closes the window
  unless an active interaction consumes it first.
- Middle-click over the page or blank margins starts vertical autoscroll with a
  circular anchor. Moving beyond its 10 px dead zone controls direction and speed,
  increasing with distance up to 2400 px/second. A click latches the mode, while a
  held middle drag stops on release. Another click or Escape cancels without
  activating the control underneath. Wheel input, navigation, hiding, minimizing
  and window deactivation stop the timer and release mouse capture.
- Use the UI theme font and readable text/background/link colors. Long paragraphs
  wrap without requiring horizontal scrolling at the minimum supported width.
  The initial size fits the available desktop work area, including smaller screens.
  Center the reading area with a maximum width of 880 logical pixels, retaining
  left-aligned text. Keep the navigation row in the same centered column, with
  its first button aligned to the text's left edge, including the document inset.
  The scrollbar stays at the window's right edge. Mouse-wheel scrolling works
  over the reading column, blank side margins and outer margins. Only the reading
  column uses the field background, while margins use the window background.
  Font and paragraph spacing stay identical on first load,
  Home, history navigation and theme changes; polish the widget before importing
  Markdown so application styling cannot alter an already imported page's metrics.
- Missing or out-of-guide local links show an inline notice and retain the current
  page. Home remains usable. Only explicit HTTP/HTTPS links open an external browser.
- Help navigation and text focus must not trigger canvas editing shortcuts.
- About is a standalone frameless dialog matching Stacker's About layout:
  minimum width 600, margins 24/24/24/18, 300-pixel logo, centered version,
  copyright and wrapped description, followed by Github, Report Issue and
  Licenses links. A click elsewhere dismisses it; Escape also closes it.
  Both the About menu action and the ordinary relative `about` link in Help open
  this dialog. `about` is a navigation action, not a Markdown document. The link
  leaves the current help page and navigation history intact. A future web help
  host should route this same link to its About dialog. Markdown syntax remains
  standard; the host provides the link's navigation behavior.

Qt's QTextBrowser supplies rendering and navigation. No custom Markdown parser
is needed. A web port should use an established CommonMark renderer, the same
source pages and equivalent navigation, focus, styling and scrolling behavior.
The rendering adapter belongs to the UI framework; documentation remains portable.

## Reading typography

These are application styling rules, applied after Markdown parsing. Keep them
out of document source. Values below use logical pixels unless stated otherwise.
A web implementation should implement equivalent styles in its help stylesheet.

- Body: UI theme font at 11 pt (approximately 14.67 CSS px at 96 logical DPI),
  left aligned, with a minimum line box of 1.5 em. Body paragraphs have 0 top
  margin and 12 bottom margin. Long text wraps inside the existing 880-pixel
  column and its 20-pixel document inset.
- Headings: semibold (600); size multipliers for levels 1 through 6 are
  2, 1.5, 1.25, 1.1, 1 and 1. Top margins are 32, 28, 24, 20, 18 and 18;
  bottom margins are 20, 14, 10, 8, 8 and 8. The first document heading has
  no top margin. Heading line boxes are at least 1.25 times their font size.
- Inline code: fixed-pitch font at 12 pt and semibold (600), with horizontal
  padding and a tinted background. Fenced code retains the 11 pt body size.
- List items: body line spacing and a 6-pixel bottom margin; preserve numbering,
  nesting and the renderer's semantic list structure.
- Standalone images: 8 top and 16 bottom margin. Never enlarge beyond intrinsic
  size; shrink to the available content width, retaining aspect ratio. Inline
  media can increase its line's height so it is never clipped by text spacing.
  Local animated GIFs play using their authored frame timing and loop behavior.
  Playback must preserve selection, scroll position, document layout and history.
  Pause when Help is hidden or minimized, resume when restored, and dispose of
  decoders when changing pages or closing. Repeated references share a decoder;
  decode frames on demand rather than retaining every frame in memory. A web
  renderer should retain normal animated-image behavior for the same Markdown.
- Tables: no outer border or cell gridlines. Cell padding is 8 on every side,
  cell spacing is 0; table top/bottom margins are 8/16. Cell paragraphs have
  no top/bottom margin. Preserve the imported header emphasis and column alignment.

Qt applies native QTextBlockFormat, QTextCharFormat and QTextTableFormat values;
it does not rewrite Markdown into custom HTML or use a custom parser. Minimum
line heights accommodate tall glyphs and images. Reapplying styles must be
idempotent, including Home, history navigation and UI theme changes.

## Packaging and validation

Distribute the complete `docs/help` folder at the application resource directory's
`docs/help` path. The desktop viewer resolves it relative to the application, not
the working directory. A web build must serve these pages as bundled resources
and translate their relative page links to help navigation.

From the workspace root, run:

```text
python checks/run_checks.py check_help_docs.py check_help_viewer.py check_header_menus.py
python checks/run_checks.py check_help_typography.py check_help_code.py check_help_autoscroll.py
python checks/run_checks.py check_help_animation.py
python checks/run_checks.py check_about_dialog.py
```

The documentation check enforces the chosen authoring subset and checks local
links and landing-page reachability. The UI check exercises real Qt rendering,
navigation, focus isolation, themes and window reuse. Its diagnostic captures
should also be inspected after layout or theme changes. These checks do not claim
pixel equivalence with a future browser renderer; verify that port with the same
pages, small viewport sizes, link navigation and theme/focus scenarios.
