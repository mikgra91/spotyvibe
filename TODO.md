# CSS Split Plan — `styles.css` (4,810 lines → 11 files)

## Goal
Split the monolithic `frontend/static/css/styles.css` into logical modules for better maintainability.

## Proposed Files & Load Order

Files must be loaded in this order in `base.html` (tokens first, responsive last):

### 1. `base.css` (~170 lines)
- [ ] Design tokens (`:root` CSS custom properties)
- [ ] Z-index scale comment block
- [ ] Reset (margin, padding, box-sizing)
- [ ] Body background (gradients, vignette `::after`)
- [ ] Background canvas container
- [ ] `@media (prefers-reduced-motion: reduce)` base rules
- [ ] Scrollbar styling (WebKit + Firefox)

### 2. `layout.css` (~80 lines)
- [ ] `.container` (max-width, responsive padding, safe-area-inset)
- [ ] Typography (`h1`, `.subtitle`, `.inline-divider`)
- [ ] `.sr-only`, `.skip-link`
- [ ] `:focus-visible` global rule
- [ ] `.hidden` utility

### 3. `buttons.css` (~150 lines)
- [ ] `.btn` base styles (pill shape, transitions, disabled state)
- [ ] `.btn-like`, `.btn-save` (primary green)
- [ ] `.btn-dislike` (error red)
- [ ] `.btn-remove`, `.btn-cancel` (secondary dark)
- [ ] `.btn-secondary` (transparent + border)
- [ ] `.btn-run` (large CTA, gradient + glow)
- [ ] `.btn-run-cancel` (error variant)
- [ ] `.btn-use-tracks` (outlined primary)

### 4. `forms.css` (~180 lines)
- [ ] `.form-row`, labels, `.form-hint`
- [ ] Input, select, textarea base styling + focus states
- [ ] Select custom chevron (SVG data-URI)
- [ ] `.checkbox-row`, `.checkbox-label`
- [ ] `.cred-input-wrap`
- [ ] `.playlist-name-input`, `.playlist-refresh-btn`, `.playlist-delete-btn`
- [ ] `.cost-warning`
- [ ] `.playlist-form-row`

### 5. `components.css` (~550 lines)
- [ ] Glass panel shared base (`.train-section`, `.generate-section`, etc.)
- [ ] Status messages (`.status`, `.error`, `.success`, `.info`)
- [ ] `.playlist-link-box`
- [ ] Toast notifications (`.toast`, variants, positioning)
- [ ] Tooltip system (`.tooltip-trigger`, `::after`, `::before`)
- [ ] Spinner (`.spinner`, size variants, reduced-motion)
- [ ] Style switcher (`.style-switcher`, `.style-switcher-btn`, canvas)
- [ ] Section jump bubble (`.section-jump-bubble`, glow, pseudo-border, pulse animation)
- [ ] Language toggle (`.lang-toggle`, `.lang-toggle-btn`)
- [ ] Burger menu (`.burger-btn`, `.burger-icon`, animated lines)
- [ ] Settings dropdown (`.settings-dropdown`)
- [ ] Accordion panels (`.accordion-panel`, header, chevron, body, max-height animation)

### 6. `tracks.css` (~300 lines)
- [ ] `.track-list` container
- [ ] `.track-item` (glass panel, hover glow)
- [ ] `.track-header` (flex layout)
- [ ] `.track-cover-wrap` + play overlay (`::before`, `::after`)
- [ ] `.track-info`, `.track-name`, `.track-reason`
- [ ] `.track-actions`
- [ ] `.no-preview-badge`
- [ ] `.feedback-form` (collapsed/open)
- [ ] `.songlist-counter`

### 7. `modals.css` (~200 lines)
- [ ] `.modal-overlay` (fixed, backdrop-blur)
- [ ] `.modal` (glass panel, max-width, max-height)
- [ ] Modal typography (`h2`, credential status)
- [ ] `.modal-actions`
- [ ] `.modal-loading` spinner overlay
- [ ] Help modal (`.help-modal-wrapper`, `.section-help-wrapper`)
- [ ] Help content markdown rendering (h2–h4, lists, links, blockquotes, code, pre, tables)
- [ ] Screenshot lightbox

### 8. `quickstart.css` (~900 lines)
- [ ] `.quickstart-wrapper`, `.quickstart-modal` layout
- [ ] `.qs-page` scrollable content
- [ ] `.qs-footer-container` fixed footer
- [ ] `.qs-close-btn`
- [ ] Table of contents (`.qs-toc-entry`, `.qs-toc-num`, `.qs-toc-arrow`)
- [ ] Step pages (`.qs-page-header`, `.qs-page-title`, `.qs-key-actions`)
- [ ] Pagination (`.qs-pagination`, `.qs-pag-dots`, prev/next)
- [ ] Dismiss checkbox
- [ ] Demo player (`.qs-demo-player`, viewport, controls, caption)
- [ ] All `qd-*` mockup classes (scene, header, logo, modal, fields, buttons, provider sections, accordion, status pills, track cards, growth bars, cursor, animations)
- [ ] All `qd-*` keyframes (`qd-grow`, `qd-spin`, `qd-cursor-pulse`, `qd-element-pulse`, `qd-fade`, `qd-pop-in`, `qd-typing-cursor`)

### 9. `sections.css` (~700 lines)
- [ ] Train profile header (`.train-header`, left/right actions)
- [ ] Profile menu system (`.profile-menu-trigger`, `.profile-menu-dropdown`, menu items)
- [ ] Profile selector (`.profile-select-card`, `.custom-dropdown`, `.custom-dropdown-list`)
- [ ] Profile creation (`.profile-create-card`, `.profile-create-input`, confirm button, `slideDown` keyframe)
- [ ] Training input (textarea, `.train-spinner`, `.spinner`, `.train-success`, `fadeOut` keyframe)
- [ ] Band/song analysis (`.analysis-inputs`, `.analysis-input-row`, `.analysis-card`, `.analysis-title`)
- [ ] Analysis details (characteristics table, suggestions, copy button)
- [ ] Audio feature bars (`.af-grid`, `.af-row`, `.af-bar-track`, `.af-bar-fill`)
- [ ] Audio filter subpanel (`.audio-filter-subpanel`, toggle, grid, row, hint, use/clear buttons)
- [ ] Track links & metadata utilities
- [ ] Playlist mode selector, run history
- [ ] Provider sections (`.provider-section`, `.provider-openai`, `.provider-spotify`)
- [ ] Provider header, badge, subtitle, status pills, dependency chips
- [ ] Metadata result cards (`.meta-block`, `.meta-grid`, `.meta-key`, `.meta-value`)
- [ ] Confidence & warning badges

### 10. `preview.css` (~250 lines)
- [ ] `.spotify-preview-overlay` (fixed, flex, z-index 500)
- [ ] `.preview-layout` (horizontal flex)
- [ ] `.spotify-preview-panel` (player, 42vw width)
- [ ] Close button, title
- [ ] Slider + nav arrows (`.spotify-preview-prev`, `.spotify-preview-next`)
- [ ] Counter
- [ ] Tab actions (`.preview-tab-actions`, `.preview-tab`, like/dislike/dismiss states)
- [ ] Feedback panel (`.preview-feedback-panel`, expand animation, top border colors)
- [ ] Feedback form (inputs, buttons)

### 11. `responsive.css` (~700 lines)
- [ ] `@media (max-width: 768px)` — tablet overrides
- [ ] `@media (max-width: 480px)` — phone overrides (bottom-sheet modals, column layouts, touch targets, iOS 16px input fix)
- [ ] `@media (max-width: 360px)` — small phone overrides
- [ ] Onboarding screen (`.onboarding-body`, continue button)

---

## Integration

- [ ] Create all 11 CSS files in `frontend/static/css/`
- [ ] Update `frontend/templates/base.html` — replace single `<link>` with 11 `<link>` tags in load order above
- [ ] Delete original `styles.css` (or rename to `styles.css.bak` until verified)
- [ ] Verify no `@import` or JS references to `styles.css` filename
- [ ] Visual regression test across all pages/modals

## Notes

- **No build system** — Flask serves static files directly; 11 requests is fine with HTTP/2
- **Cascade order matters** — `base.css` first (tokens), `responsive.css` last (overrides)
- **Design tokens** in `base.css` are inherited by all subsequent files via CSS custom properties
- **Responsive consolidated** — all media queries in one file avoids fragmentation without a bundler
- **Biggest win**: `quickstart.css` (~900 lines, self-contained `qs-*`/`qd-*` prefixes, used by 1 modal)
