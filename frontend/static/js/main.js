import { checkCredentialStatus, checkSpotifyAuth, connectSpotify, toggleSpotifyConnection, fetchSettingsState } from './modules/auth.js';
import { renderComponentWarnings } from './modules/warnings.js';
import { toggleAccordion, prefillTrainFields, updateTrainToggleLabel, toggleTrainBody, startImportProfile, exportProfile, submitProfile, sendTrainProfile, saveProfileDirect, resetProfileToHistory, bindProfileImportInput, checkProfileStatus, loadProfileList, switchProfile, toggleCreateProfile, createNewProfile, deleteCurrentProfile, initCustomProfileDropdown, toggleProfileMenu, initProfileMenu } from './modules/profile.js';
import { toggleHistoryBody, loadHistory } from './modules/history.js';
import { toggleAnalysisBody, runAnalysis, renderAnalysisResult, copySuggestion, jumpToAnalysis } from './modules/analysis.js';
import { toggleGenerateBody, runPipeline, setGenerating, updateUseTracksButton, generateUUID, handleStreamEvent, showSseDisconnectBanner, resumeRun, cancelGeneration, useCurrentTracks, canGenerate } from './modules/pipeline.js';
import { toggleAudioFilters, getAudioFilters, clearAllFilters, updateFilterHint, applyAnalysisFilter, applyAllAnalysisFilters, updateAllFilterHints } from './modules/audio-filters.js';
import { getPlaylistMode, onPlaylistModeChange, getPlaylistModePayload, refreshDiscoverPlaylistPicker } from './modules/playlist-mode.js';
import { renderTracks } from './modules/tracklist.js';
import { openPreviewOverlay, closePreviewOverlay, prevPreview, nextPreview, previewLike, previewDislike, previewDismiss, submitPreviewFeedback, closePreviewFeedback } from './modules/preview.js';
import { toggleFeedback, closeFeedback, submitFeedback, removeTrack, animateRemove } from './modules/feedback.js';
import { toggleReviewBody, loadPlaylistTracks, renderReviewTracks, toggleReviewFeedback, closeReviewFeedback, submitReviewFeedback, dismissReviewTrack, populateReviewPlaylistPicker, refreshReviewPlaylistPicker, deleteSelectedPlaylist } from './modules/review.js';
import { showStatus, showStatusHtml, showPlaylistLink, hidePlaylistLink, esc, attr, sanitizeHtml, escHtml, toggleSettingsMenu, showToast } from './modules/ui.js';
import { openCredentials, saveCredentials, clearCredential, saveSettings, openSettings, openHelp, openSectionHelp, closeSectionHelp, openDataDir, closeModal, openQuickstart, closeQuickstart, maybeShowQuickstart } from './modules/modals.js';
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
import * as PlaylistSeed from './modules/playlist_seed.js';

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
window.previewLike = previewLike;
window.previewDislike = previewDislike;
window.previewDismiss = previewDismiss;
window.submitPreviewFeedback = submitPreviewFeedback;
window.closePreviewFeedback = closePreviewFeedback;
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
window.openHelp = openHelp;
window.openSectionHelp = openSectionHelp;
window.closeSectionHelp = closeSectionHelp;
window.openDataDir = openDataDir;
window.closeModal = closeModal;
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
window.openModal = function(id) { const el = document.getElementById(id); if (el) el.classList.add('open'); };

// Listen for spotify auth popup callback
window.addEventListener('message', async (e) => {
    if (e.data === 'spotify-auth-complete') {
        await checkSpotifyAuth();
        renderComponentWarnings();
    }
});

// Close settings dropdown when clicking outside
document.addEventListener('click', (e) => {
    const wrapper = document.querySelector('.header-controls');
    if (wrapper && !wrapper.contains(e.target)) {
        document.getElementById('settingsDropdown').classList.remove('open');
    }
});

// DOMContentLoaded init
document.addEventListener('DOMContentLoaded', async () => {
    // Overlay click-to-close
    const overlay = document.getElementById('spotifyPreviewOverlay');
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

    // Show refresh button when running inside pywebview desktop wrapper
    if (window.pywebview) {
        const rb = document.getElementById('refreshBtn');
        if (rb) rb.classList.remove('hidden');
    }

    // Auth and warnings
    Promise.all([checkCredentialStatus(), checkSpotifyAuth(), fetchSettingsState()]).then(() => {
        renderComponentWarnings();
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

    // i18n
    await initI18n();

    // Tab navigation
    initTabs();

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

    // Quickstart guide (auto-show on first visit for the active provider)
    maybeShowQuickstart(getActiveProvider());
});
