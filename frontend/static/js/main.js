import { checkCredentialStatus, checkSpotifyAuth, connectSpotify, toggleSpotifyConnection, fetchSettingsState } from './modules/auth.js';
import { renderComponentWarnings } from './modules/warnings.js';
import { toggleAccordion, prefillTrainFields, updateTrainToggleLabel, toggleTrainBody, startImportProfile, exportProfile, submitProfile, sendTrainProfile, saveProfileDirect, resetProfileToHistory, bindProfileImportInput, checkProfileStatus, loadProfileList, switchProfile, toggleCreateProfile, createNewProfile, deleteCurrentProfile, initCustomProfileDropdown, toggleProfileMenu, initProfileMenu, updateSeedCardState } from './modules/profile.js';
import { toggleHistoryBody, loadHistory } from './modules/history.js';
import { toggleAnalysisBody, runAnalysis, renderAnalysisResult, copySuggestion, jumpToAnalysis } from './modules/analysis.js';
import { toggleGenerateBody, runPipeline, setGenerating, updateUseTracksButton, generateUUID, handleStreamEvent, showSseDisconnectBanner, resumeRun, cancelGeneration, useCurrentTracks, canGenerate } from './modules/pipeline.js';
import { toggleAudioFilters, getAudioFilters, clearAllFilters, updateFilterHint, applyAnalysisFilter, applyAllAnalysisFilters, updateAllFilterHints } from './modules/audio-filters.js';
import { getPlaylistMode, onPlaylistModeChange, getPlaylistModePayload, refreshDiscoverPlaylistPicker, initPlaylistMode } from './modules/playlist-mode.js';
import { renderTracks } from './modules/tracklist.js';
import { openPreviewOverlay, closePreviewOverlay, prevPreview, nextPreview, quickLike, quickDislike, previewDismiss, submitPreviewFeedback, closePreviewFeedback, openPreviewFeedbackPanel, togglePreviewAutoplay, sdkTogglePlay } from './modules/preview.js';
import { toggleFeedback, closeFeedback, submitFeedback, removeTrack, animateRemove } from './modules/feedback.js';
import { toggleReviewBody, loadPlaylistTracks, renderReviewTracks, toggleReviewFeedback, closeReviewFeedback, submitReviewFeedback, dismissReviewTrack, populateReviewPlaylistPicker, refreshReviewPlaylistPicker, deleteSelectedPlaylist } from './modules/review.js';
import { showStatus, showStatusHtml, showPlaylistLink, hidePlaylistLink, esc, attr, sanitizeHtml, escHtml, toggleSettingsMenu, showToast } from './modules/ui.js';
import { openCredentials, saveCredentials, clearCredential, saveSettings, openSettings, openHelp, openSectionHelp, closeSectionHelp, openDataDir, closeModal, dismissHelpBanner, dismissSectionHelpBanner, openQuickstart, closeQuickstart, maybeShowQuickstart } from './modules/modals.js';
import { quickstartGoTo, quickstartNext, quickstartPrev } from './modules/quickstart-tour.js';
import { qsDemoNext, qsDemoPrev, qsDemoToggle, qsDemoExpand, initAllDemos, destroyAllDemos } from './modules/quickstart-demo.js';
import { switchTheme, THEME_BACKGROUNDS, THEME_RENDERERS } from './modules/theme-switcher.js';
import { initTabs, switchTab, getActiveProvider } from './modules/tabs.js';
import './modules/theme-calm.js';
import './modules/theme-equalizer.js';
import './modules/theme-pulse.js';
import './modules/theme-spectrum.js';
import './modules/theme-starfield.js';
import { switchLanguage, applyLanguage, i18n, _i18nStrings, initI18n } from './modules/i18n.js';
import { renderProviderPills } from './modules/provider-pills.js';
import * as Completeness from './modules/completeness.js';
import * as Exploration from './modules/exploration.js';
import * as Presets from './modules/presets.js';
import * as QuickAdvanced from './modules/quick_advanced.js';
import * as Tips from './modules/tips.js';
import * as Rationale from './modules/rationale.js';
import * as TasteDashboard from './modules/taste_dashboard.js';
import { toggleDashboardBody } from './modules/taste_dashboard.js';
import * as PlaylistSeed from './modules/playlist_seed.js';
import * as Provider from './modules/provider.js';
import * as CostEstimate from './modules/cost_estimate.js';
import * as Voice from './modules/voice.js';
import { initGettingStarted, refreshGettingStarted } from './modules/getting-started.js';
import { initUiScale, setUiScale } from './modules/ui-scale.js';
import { el } from './modules/dom.js';

// Expose globals for HTML onclick= attributes
window.checkCredentialStatus = checkCredentialStatus;
window.checkSpotifyAuth = checkSpotifyAuth;
window.connectSpotify = connectSpotify;
window.toggleSpotifyConnection = toggleSpotifyConnection;
window.fetchSettingsState = fetchSettingsState;
window.renderComponentWarnings = renderComponentWarnings;
window.toggleAccordion = toggleAccordion;
window.prefillTrainFields = prefillTrainFields;
window.updateTrainToggleLabel = updateTrainToggleLabel;
window.toggleTrainBody = toggleTrainBody;
window.startImportProfile = startImportProfile;
window.exportProfile = exportProfile;
window.submitProfile = submitProfile;
window.sendTrainProfile = sendTrainProfile;
window.saveProfileDirect = saveProfileDirect;
window.resetProfileToHistory = resetProfileToHistory;
window.loadProfileList = loadProfileList;
window.switchProfile = switchProfile;
window.toggleCreateProfile = toggleCreateProfile;
window.createNewProfile = createNewProfile;
window.deleteCurrentProfile = deleteCurrentProfile;
window.toggleProfileMenu = toggleProfileMenu;
window.toggleHistoryBody = toggleHistoryBody;
window.loadHistory = loadHistory;
window.toggleAnalysisBody = toggleAnalysisBody;
window.toggleDashboardBody = toggleDashboardBody;
window.jumpToAnalysis = jumpToAnalysis;
window.runAnalysis = runAnalysis;
window.renderAnalysisResult = renderAnalysisResult;
window.copySuggestion = copySuggestion;
window.runPipeline = runPipeline;
window.toggleGenerateBody = toggleGenerateBody;
window.setGenerating = setGenerating;
window.updateUseTracksButton = updateUseTracksButton;
window.generateUUID = generateUUID;
window.handleStreamEvent = handleStreamEvent;
window.showSseDisconnectBanner = showSseDisconnectBanner;
window.resumeRun = resumeRun;
window.cancelGeneration = cancelGeneration;
window.useCurrentTracks = useCurrentTracks;
window.canGenerate = canGenerate;
window.toggleAudioFilters = toggleAudioFilters;
window.getAudioFilters = getAudioFilters;
window.clearAllFilters = clearAllFilters;
window.updateFilterHint = updateFilterHint;
window.applyAnalysisFilter = applyAnalysisFilter;
window.applyAllAnalysisFilters = applyAllAnalysisFilters;
window.getPlaylistMode = getPlaylistMode;
window.onPlaylistModeChange = onPlaylistModeChange;
window.getPlaylistModePayload = getPlaylistModePayload;
window.refreshDiscoverPlaylistPicker = refreshDiscoverPlaylistPicker;
window.renderTracks = renderTracks;
window.openPreviewOverlay = openPreviewOverlay;
window.closePreviewOverlay = closePreviewOverlay;
window.prevPreview = prevPreview;
window.nextPreview = nextPreview;
window.quickLike = quickLike;
window.quickDislike = quickDislike;
window.previewDismiss = previewDismiss;
window.submitPreviewFeedback = submitPreviewFeedback;
window.closePreviewFeedback = closePreviewFeedback;
window.openPreviewFeedbackPanel = openPreviewFeedbackPanel;
window.togglePreviewAutoplay = togglePreviewAutoplay;
window.sdkTogglePlay = sdkTogglePlay;
window.toggleFeedback = toggleFeedback;
window.closeFeedback = closeFeedback;
window.submitFeedback = submitFeedback;
window.removeTrack = removeTrack;
window.animateRemove = animateRemove;
window.toggleReviewBody = toggleReviewBody;
window.loadPlaylistTracks = loadPlaylistTracks;
window.renderReviewTracks = renderReviewTracks;
window.toggleReviewFeedback = toggleReviewFeedback;
window.closeReviewFeedback = closeReviewFeedback;
window.submitReviewFeedback = submitReviewFeedback;
window.dismissReviewTrack = dismissReviewTrack;
window.populateReviewPlaylistPicker = populateReviewPlaylistPicker;
window.refreshReviewPlaylistPicker = refreshReviewPlaylistPicker;
window.deleteSelectedPlaylist = deleteSelectedPlaylist;
window.showStatus = showStatus;
window.showPlaylistLink = showPlaylistLink;
window.hidePlaylistLink = hidePlaylistLink;
window.esc = esc;
window.attr = attr;
window.sanitizeHtml = sanitizeHtml;
window.escHtml = escHtml;
window.toggleSettingsMenu = toggleSettingsMenu;
window.showToast = showToast;
window.openCredentials = openCredentials;
window.saveCredentials = saveCredentials;
window.clearCredential = clearCredential;
window.saveSettings = saveSettings;
window.openSettings = openSettings;
window.setUiScale = setUiScale;
window.openHelp = openHelp;
window.openSectionHelp = openSectionHelp;
window.closeSectionHelp = closeSectionHelp;
window.openDataDir = openDataDir;
window.closeModal = closeModal;
window.dismissHelpBanner = dismissHelpBanner;
window.dismissSectionHelpBanner = dismissSectionHelpBanner;
window.openQuickstart = openQuickstart;
window.closeQuickstart = closeQuickstart;
window.quickstartGoTo = quickstartGoTo;
window.quickstartNext = quickstartNext;
window.quickstartPrev = quickstartPrev;
window.qsDemoNext = qsDemoNext;
window.qsDemoPrev = qsDemoPrev;
window.qsDemoToggle = qsDemoToggle;
window.qsDemoExpand = qsDemoExpand;
window.switchTheme = switchTheme;
window.switchTab = switchTab;
window.getActiveProvider = getActiveProvider;
window.maybeShowQuickstart = maybeShowQuickstart;
window.switchLanguage = switchLanguage;
window.applyLanguage = applyLanguage;
window.i18n = i18n;
window.renderProviderPills = renderProviderPills;
window.togglePresetDropdown = Presets.togglePresetDropdown;
window.confirmSaveAsPreset = Presets.confirmSaveAsPreset;
window.importPresetFile = Presets.importPresetFile;
window._explorationModule = Exploration;
window.openModal = function(id) { const node = el(id); if (node) node.classList.add('open'); };

// Wave 2+: functions referenced via onclick= in templates
window.toggleCompletenessDetail = Completeness.toggleCompletenessDetail;
window.confirmPlaylistSeed = PlaylistSeed.confirmPlaylistSeed;
window.discardProfileDraft = PlaylistSeed.discardProfileDraft;
window.openPlaylistSeedPicker = PlaylistSeed.openPlaylistSeedPicker;
window.resetTipsSeen = Tips.resetTipsSeen;
window.fetchProviderModels = Provider.fetchProviderModels;
window.toggleModelFreeText = Provider.toggleModelFreeText;
window.toggleCostPopover = CostEstimate.toggleCostPopover;
window.toggleVoice = Voice.toggleVoice;

// Listen for spotify auth popup callback
window.addEventListener('message', async (e) => {
    if (e.data === 'spotify-auth-complete') {
        await checkSpotifyAuth();
        renderComponentWarnings();
        updateSeedCardState();
        if (typeof window.refreshGettingStarted === 'function') window.refreshGettingStarted();
    }
});

// Close settings dropdown when clicking outside
document.addEventListener('click', (e) => {
    const wrapper = document.querySelector('.header-controls');
    if (wrapper && !wrapper.contains(e.target)) {
        el('settingsDropdown').classList.remove('open');
    }
});

// DOMContentLoaded init
document.addEventListener('DOMContentLoaded', async () => {
    // Overlay click-to-close
    const overlay = el('spotifyPreviewOverlay');
    if (overlay) {
        overlay.addEventListener('click', function(e) {
            if (e.target === this) closePreviewOverlay();
        });
    }

    // Restore saved theme (renderers are registered via side-effect imports above)
    let _pendingTheme = null;
    try {
        const saved = localStorage.getItem('spotyvibe-theme');
        if (saved && THEME_BACKGROUNDS[saved]) _pendingTheme = saved;
    } catch(e) {}
    switchTheme(_pendingTheme || 'calm');

    // Restore saved UI text-size preference (§9 Phase 2)
    initUiScale();

    // Show refresh button when running inside pywebview desktop wrapper
    if (window.pywebview) {
        const rb = el('refreshBtn');
        if (rb) rb.classList.remove('hidden');
    }

    // Auth and warnings — fetch settings first (sets llmApiKeyRequired),
    // then check credentials (which reads it to skip key check for local providers)
    fetchSettingsState().then(() =>
        Promise.all([checkCredentialStatus(), checkSpotifyAuth()])
    ).then(() => {
        renderComponentWarnings();
        updateSeedCardState();
    });

    // Profile
    initCustomProfileDropdown();
    initProfileMenu();
    await loadProfileList();
    checkProfileStatus();
    updateTrainToggleLabel();
    bindProfileImportInput();

    // Playlist mode
    onPlaylistModeChange();
    initPlaylistMode();

    // Tab navigation — wire click handlers before awaiting i18n so tests
    // (and fast users) don't click a tab before listeners are attached.
    initTabs();

    // i18n
    await initI18n();

    // Wave 2: Quick/Advanced mode, exploration slider, presets, completeness
    QuickAdvanced.init();
    Exploration.init();
    Presets.init();
    Completeness.init();

    // Wave 3: Tips, rationale, taste dashboard, playlist seed
    Tips.init();
    Rationale.init();
    TasteDashboard.init();
    PlaylistSeed.init();
    PlaylistSeed.applyPendingDraftIfAny();

    // Wave 4: Provider, cost estimate, voice
    Provider.init();
    CostEstimate.init();
    Voice.init();

    // Wave 5: Getting Started checklist (replaces auto-tour)
    initGettingStarted();

});
