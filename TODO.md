# CSS Split Plan — `styles.css` (4,810 lines → 11 files)

## Goal
Split the monolithic `frontend/static/css/styles.css` into logical modules for better maintainability.

## Proposed Files & Load Order

Files must be loaded in this order in `base.html` (tokens first, responsive last):

### 1. `base.css` (~170 lines)
- [x] Design tokens (`:root` CSS custom properties)
- [x] Z-index scale comment block
- [x] Reset (margin, padding, box-sizing)
- [x] Body background (gradients, vignette `::after`)
- [x] Background canvas container
- [x] `@media (prefers-reduced-motion: reduce)` base rules
- [x] Scrollbar styling (WebKit + Firefox)

### 2. `layout.css` (~80 lines)
- [x] `.container` (max-width, responsive padding, safe-area-inset)
- [x] Typography (`h1`, `.subtitle`, `.inline-divider`)
- [x] `.sr-only`, `.skip-link`
- [x] `:focus-visible` global rule
- [x] `.hidden` utility

### 3. `buttons.css` (~150 lines)
- [x] `.btn` base styles (pill shape, transitions, disabled state)
- [x] `.btn-like`, `.btn-save` (primary green)
- [x] `.btn-dislike` (error red)
- [x] `.btn-remove`, `.btn-cancel` (secondary dark)
- [x] `.btn-secondary` (transparent + border)
- [x] `.btn-run` (large CTA, gradient + glow)
- [x] `.btn-run-cancel` (error variant)
- [x] `.btn-use-tracks` (outlined primary)

### 4. `forms.css` (~180 lines)
- [x] `.form-row`, labels, `.form-hint`
- [x] Input, select, textarea base styling + focus states
- [x] Select custom chevron (SVG data-URI)
- [x] `.checkbox-row`, `.checkbox-label`
- [x] `.cred-input-wrap`
- [x] `.playlist-name-input`, `.playlist-refresh-btn`, `.playlist-delete-btn`
- [x] `.cost-warning`
- [x] `.playlist-form-row`

### 5. `components.css` (~550 lines)
- [x] Glass panel shared base (`.train-section`, `.generate-section`, etc.)
- [x] Status messages (`.status`, `.error`, `.success`, `.info`)
- [x] `.playlist-link-box`
- [x] Toast notifications (`.toast`, variants, positioning)
- [x] Tooltip system (`.tooltip-trigger`, `::after`, `::before`)
- [x] Spinner (`.spinner`, size variants, reduced-motion)
- [x] Style switcher (`.style-switcher`, `.style-switcher-btn`, canvas)
- [x] Section jump bubble (`.section-jump-bubble`, glow, pseudo-border, pulse animation)
- [x] Language toggle (`.lang-toggle`, `.lang-toggle-btn`)
- [x] Burger menu (`.burger-btn`, `.burger-icon`, animated lines)
- [x] Settings dropdown (`.settings-dropdown`)
- [x] Accordion panels (`.accordion-panel`, header, chevron, body, max-height animation)

### 6. `tracks.css` (~300 lines)
- [x] `.track-list` container
- [x] `.track-item` (glass panel, hover glow)
- [x] `.track-header` (flex layout)
- [x] `.track-cover-wrap` + play overlay (`::before`, `::after`)
- [x] `.track-info`, `.track-name`, `.track-reason`
- [x] `.track-actions`
- [x] `.no-preview-badge`
- [x] `.feedback-form` (collapsed/open)
- [x] `.songlist-counter`

### 7. `modals.css` (~200 lines)
- [x] `.modal-overlay` (fixed, backdrop-blur)
- [x] `.modal` (glass panel, max-width, max-height)
- [x] Modal typography (`h2`, credential status)
- [x] `.modal-actions`
- [x] `.modal-loading` spinner overlay
- [x] Help modal (`.help-modal-wrapper`, `.section-help-wrapper`)
- [x] Help content markdown rendering (h2–h4, lists, links, blockquotes, code, pre, tables)
- [x] Screenshot lightbox

### 8. `quickstart.css` (~900 lines)
- [x] `.quickstart-wrapper`, `.quickstart-modal` layout
- [x] `.qs-page` scrollable content
- [x] `.qs-footer-container` fixed footer
- [x] `.qs-close-btn`
- [x] Table of contents (`.qs-toc-entry`, `.qs-toc-num`, `.qs-toc-arrow`)
- [x] Step pages (`.qs-page-header`, `.qs-page-title`, `.qs-key-actions`)
- [x] Pagination (`.qs-pagination`, `.qs-pag-dots`, prev/next)
- [x] Dismiss checkbox
- [x] Demo player (`.qs-demo-player`, viewport, controls, caption)
- [x] All `qd-*` mockup classes (scene, header, logo, modal, fields, buttons, provider sections, accordion, status pills, track cards, growth bars, cursor, animations)
- [x] All `qd-*` keyframes (`qd-grow`, `qd-spin`, `qd-cursor-pulse`, `qd-element-pulse`, `qd-fade`, `qd-pop-in`, `qd-typing-cursor`)

### 9. `sections.css` (~700 lines)
- [x] Train profile header (`.train-header`, left/right actions)
- [x] Profile menu system (`.profile-menu-trigger`, `.profile-menu-dropdown`, menu items)
- [x] Profile selector (`.profile-select-card`, `.custom-dropdown`, `.custom-dropdown-list`)
- [x] Profile creation (`.profile-create-card`, `.profile-create-input`, confirm button, `slideDown` keyframe)
- [x] Training input (textarea, `.train-spinner`, `.spinner`, `.train-success`, `fadeOut` keyframe)
- [x] Band/song analysis (`.analysis-inputs`, `.analysis-input-row`, `.analysis-card`, `.analysis-title`)
- [x] Analysis details (characteristics table, suggestions, copy button)
- [x] Audio feature bars (`.af-grid`, `.af-row`, `.af-bar-track`, `.af-bar-fill`)
- [x] Audio filter subpanel (`.audio-filter-subpanel`, toggle, grid, row, hint, use/clear buttons)
- [x] Track links & metadata utilities
- [x] Playlist mode selector, run history
- [x] Provider sections (`.provider-section`, `.provider-openai`, `.provider-spotify`)
- [x] Provider header, badge, subtitle, status pills, dependency chips
- [x] Metadata result cards (`.meta-block`, `.meta-grid`, `.meta-key`, `.meta-value`)
- [x] Confidence & warning badges

### 10. `preview.css` (~250 lines)
- [x] `.spotify-preview-overlay` (fixed, flex, z-index 500)
- [x] `.preview-layout` (horizontal flex)
- [x] `.spotify-preview-panel` (player, 42vw width)
- [x] Close button, title
- [x] Slider + nav arrows (`.spotify-preview-prev`, `.spotify-preview-next`)
- [x] Counter
- [x] Tab actions (`.preview-tab-actions`, `.preview-tab`, like/dislike/dismiss states)
- [x] Feedback panel (`.preview-feedback-panel`, expand animation, top border colors)
- [x] Feedback form (inputs, buttons)

### 11. `responsive.css` (~700 lines)
- [x] `@media (max-width: 768px)` — tablet overrides
- [x] `@media (max-width: 480px)` — phone overrides (bottom-sheet modals, column layouts, touch targets, iOS 16px input fix)
- [x] `@media (max-width: 360px)` — small phone overrides
- [x] Onboarding screen (`.onboarding-body`, continue button)

---

## Integration

- [x] Create all 11 CSS files in `frontend/static/css/`
- [x] Update `frontend/templates/base.html` — replace single `<link>` with 11 `<link>` tags in load order above
- [x] Delete original `styles.css` (or rename to `styles.css.bak` until verified)
- [x] Verify no `@import` or JS references to `styles.css` filename
- [x] Visual regression test across all pages/modals

## Notes

- **No build system** — Flask serves static files directly; 11 requests is fine with HTTP/2
- **Cascade order matters** — `base.css` first (tokens), `responsive.css` last (overrides)
- **Design tokens** in `base.css` are inherited by all subsequent files via CSS custom properties
- **Responsive consolidated** — all media queries in one file avoids fragmentation without a bundler
- **Biggest win**: `quickstart.css` (~900 lines, self-contained `qs-*`/`qd-*` prefixes, used by 1 modal)
