package com.ampixa.nepakeyboard.ime;

import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Build;
import android.os.IBinder;
import android.view.KeyEvent;
import android.view.View;
import android.view.Window;
import android.view.WindowInsetsController;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.view.inputmethod.InputMethodManager;
import android.view.inputmethod.InputMethodSubtype;
import android.inputmethodservice.InputMethodService;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.widget.Toast;


/** Product IME shell driven by the generated selectable profile catalog. */
public final class NepaInputMethodService extends InputMethodService
        implements NepaInputView.Listener {
    interface SubtypeTransitionObserver {
        void onInputViewActive(
                NepaInputMethodService service,
                NepaInputView view,
                boolean legacyWindowTokenPresent
        );

        void onProductProfilePending(String profileId, String pendingProfileId);

        void onSwitchDispatched(
                String profileId,
                AndroidSubtypeRegistry.SwitchPath path,
                boolean legacyWindowTokenPresent,
                boolean dispatched
        );

        void onPlatformProfileObserved(
                String source,
                String observedProfileId,
                String activeProfileId,
                String pendingProfileId
        );
    }

    private static volatile SubtypeTransitionObserver subtypeTransitionObserver;

    private LanguagePreferences languagePreferences;
    private KeyboardPreferences keyboardPreferences;
    private TransliterationCatalog transliterationCatalog;
    private final TransliterationSession transliterationSession = new TransliterationSession();
    private EditorMode editorMode = EditorMode.OTHER;
    private AndroidSubtypeRegistry subtypeRegistry;
    private SuggestionEngine suggestionEngine;
    private ComposingSession composingSession;
    private NepaInputView inputView;
    private SuggestionSnapshot currentSuggestions;
    private boolean privateField;
    private boolean emojiHistoryAllowed;
    private int editorSelectionStart = -1;
    private int editorSelectionEnd = -1;
    private boolean inputViewActive;
    private volatile Handler mainHandler;
    private SharedPreferences.OnSharedPreferenceChangeListener preferenceStateListener;
    private String requestedSubtypeProfileId;
    private int mismatchedSubtypeCallbacks;
    private boolean languageSwitchFailureShown;
    private volatile boolean destroyed;
    private SuggestionQuery dispatchedSuggestionQuery;
    private Runnable suggestionDeadlineCallback;
    private final Runnable preferenceReconcile = this::reconcileProductPreferences;

    @Override
    public void onCreate() {
        super.onCreate();
        mainHandler = new Handler(Looper.getMainLooper());
        languagePreferences = new LanguagePreferences(this);
        keyboardPreferences = new KeyboardPreferences(this);
        try {
            subtypeRegistry = AndroidSubtypeRegistry.load(this);
        } catch (RuntimeException inconsistentPlatformMetadata) {
            // Literal typing remains available even if installed subtype metadata is stale.
            subtypeRegistry = null;
        }
        suggestionEngine = SuggestionEngineFactory.create(
                SuggestionArtifactRegistry.installed(this),
                activation -> {
                    Handler handler = mainHandler;
                    if (handler != null && !destroyed) {
                        handler.post(() -> onSuggestionStateChanged(activation));
                    }
                }
        );
        composingSession = new ComposingSession(suggestionEngine);
        transliterationCatalog = TransliterationCatalog.load(this);
        preferenceStateListener = (preferences, key) -> {
            Handler handler = mainHandler;
            if (handler != null) {
                handler.removeCallbacks(preferenceReconcile);
                handler.post(preferenceReconcile);
            }
        };
        languagePreferences.registerStateListener(preferenceStateListener);
        keyboardPreferences.registerStateListener(preferenceStateListener);
    }

    @Override
    public View onCreateInputView() {
        inputView = new NepaInputView(this, this);
        inputView.setProfile(languagePreferences.activeProfile());
        inputView.applyPreferences(keyboardPreferences);
        updateNavigationBarAppearance();
        return inputView;
    }

    @Override
    public void onStartInput(EditorInfo attribute, boolean restarting) {
        cancelDeleteRepeat();
        super.onStartInput(attribute, restarting);
    }

    @Override
    public void onStartInputView(EditorInfo attribute, boolean restarting) {
        super.onStartInputView(attribute, restarting);
        cancelDeleteRepeat();
        inputViewActive = true;
        editorMode = EditorMode.from(attribute);
        privateField = editorMode.privateField();
        emojiHistoryAllowed = !privateField
                && (attribute.imeOptions & EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING) == 0;
        updateEditorSelection(attribute.initialSelStart, attribute.initialSelEnd);
        KeyboardProfile profile = reconcileCurrentPlatformProfile();
        InputConnection connection = getCurrentInputConnection();
        if (connection != null) {
            composingSession.start(
                    profile,
                    editorMode.composingAllowed(),
                    privateField,
                    textSink(connection)
            );
        } else {
            composingSession.reset(profile, editorMode.composingAllowed(), privateField);
        }
        if (inputView != null) {
            inputView.hidePicker();
            inputView.setEmojiHistoryAllowed(emojiHistoryAllowed);
            inputView.setProfile(profile);
            inputView.setEditorMode(editorMode);
            inputView.setTransliterationAvailable(
                    transliterationCatalog != null && transliterationCatalog.supports(profile)
            );
        }
        forcePhoneticInputWhenItIsTheOnlyRoute(profile);
        transliterationSession.start(
                boundTransliterationEngine(
                        inputView != null && inputView.isTransliterating(),
                        profile
                ),
                privateField
        );
        refreshSuggestions();
        synchronizeEnabledSubtypes();
        updateNavigationBarAppearance();
        notifyInputViewActive();
        requestPendingSubtype(false);
    }

    @Override
    public boolean onEvaluateFullscreenMode() {
        return false;
    }

    @Override
    public void onFinishInput() {
        cancelSuggestionDeadline();
        cancelDeleteRepeat();
        InputConnection connection = getCurrentInputConnection();
        if (connection != null) {
            // A pending phonetic buffer is committed, not dropped: the editor already
            // shows it as composing text, so discarding it would lose typed input.
            transliterationSession.finish(textSink(connection));
            if (composingSession != null) {
                composingSession.finish(textSink(connection));
            }
        }
        inputViewActive = false;
        if (composingSession != null && languagePreferences != null) {
            composingSession.reset(languagePreferences.activeProfile(), false, false);
        }
        if (inputView != null) {
            inputView.clearSuggestions();
            inputView.hidePicker();
            inputView.setEmojiHistoryAllowed(false);
        }
        // Unbind rather than only clearing: no key may reach a stale engine before the
        // next onStartInput rebinds one for the incoming editor.
        transliterationSession.start(null, false);
        currentSuggestions = null;
        privateField = false;
        emojiHistoryAllowed = false;
        editorMode = EditorMode.OTHER;
        editorSelectionStart = -1;
        editorSelectionEnd = -1;
        super.onFinishInput();
    }

    @Override
    public void onFinishInputView(boolean finishingInput) {
        cancelSuggestionDeadline();
        cancelDeleteRepeat();
        if (composingSession != null) {
            composingSession.cancelSuggestions();
        }
        currentSuggestions = null;
        if (inputView != null) {
            inputView.clearSuggestions();
            inputView.hidePicker();
            inputView.setEmojiHistoryAllowed(false);
        }
        emojiHistoryAllowed = false;
        inputViewActive = false;
        super.onFinishInputView(finishingInput);
    }

    @Override
    public void onWindowHidden() {
        cancelDeleteRepeat();
        super.onWindowHidden();
    }

    @Override
    public void onDestroy() {
        destroyed = true;
        inputViewActive = false;
        cancelSuggestionDeadline();
        cancelDeleteRepeat();
        if (preferenceStateListener != null) {
            if (languagePreferences != null) {
                languagePreferences.unregisterStateListener(preferenceStateListener);
            }
            if (keyboardPreferences != null) {
                keyboardPreferences.unregisterStateListener(preferenceStateListener);
            }
        }
        if (suggestionEngine != null) {
            suggestionEngine.close();
        }
        if (mainHandler != null) {
            mainHandler.removeCallbacksAndMessages(null);
            mainHandler = null;
        }
        super.onDestroy();
    }

    @Override
    public void onKey(KeySpec key, SpatialKeyStroke stroke) {
        InputConnection connection = getCurrentInputConnection();
        if (!inputViewActive || connection == null || inputView == null) {
            return;
        }
        TextSink sink = textSink(connection);
        if (transliterationSession.isActive() && handleTransliterationKey(key, sink)) {
            inputView.consumeOneShotShift();
            refreshSuggestions();
            return;
        }
        switch (key.action()) {
            case TEXT:
                composingSession.appendText(key.text(), key.inputPolicy(), stroke, sink);
                inputView.consumeOneShotShift();
                break;
            case SHIFT:
                inputView.toggleShift(SystemClock.uptimeMillis());
                return;
            case DELETE:
                // The sink above owns this one snapshot. Consume the service cache
                // before mutation so a synchronous fresh callback wins the race.
                invalidateEditorSelection();
                composingSession.delete(sink);
                break;
            case ENTER:
                composingSession.commitRaw(sink);
                performEnter(connection);
                break;
            case SPACE:
                composingSession.appendText(" ", sink);
                break;
            case LANGUAGE:
                selectProductProfile(languagePreferences.cycle());
                return;
            case SYMBOLS:
                inputView.showSymbols();
                return;
            case LETTERS:
                inputView.showLetters();
                return;
            default:
                throw new IllegalStateException("unknown key action: " + key.action());
        }
        refreshSuggestions();
    }

    /**
     * Phonetic routing. Returns true when this key belonged to the Roman buffer, so the
     * direct-script path never sees it and the two sessions cannot both own a token.
     */
    private boolean handleTransliterationKey(KeySpec key, TextSink sink) {
        switch (key.action()) {
            case TEXT:
                transliterationSession.append(key.text(), sink);
                return true;
            case DELETE:
                invalidateEditorSelection();
                // Fall back to editor deletion once the Roman buffer is empty.
                return transliterationSession.deleteLast(sink);
            case SPACE:
                transliterationSession.commit(sink);
                return false;
            case ENTER:
                transliterationSession.commit(sink);
                return false;
            default:
                transliterationSession.commit(sink);
                return false;
        }
    }

    @Override
    public void onTransliterationModeChanged(boolean transliterating) {
        InputConnection connection = getCurrentInputConnection();
        KeyboardProfile profile = languagePreferences.activeProfile();
        if (connection != null) {
            TextSink sink = textSink(connection);
            // Whichever session was composing finishes cleanly before the other starts.
            transliterationSession.finish(sink);
            composingSession.finish(sink);
        }
        transliterationSession.start(
                boundTransliterationEngine(transliterating, profile),
                privateField
        );
        refreshSuggestions();
    }

    /**
     * The engine phonetic input should use, or null when phonetic input must stay off.
     *
     * <p>The catalog can be absent when its assets failed to verify, and a profile can
     * have no reviewed map, so both are treated as "phonetic input is unavailable"
     * rather than allowed to reach the session as a half-bound state.
     */
    /**
     * Turns phonetic input on for a profile that has no other way to be typed.
     *
     * <p>A transliteration-only profile has no direct-script layout and no
     * dictionary pack, so leaving the mode off would hand the user a Latin
     * keyboard that types Latin into a field they selected a Nepali language for.
     */
    private void forcePhoneticInputWhenItIsTheOnlyRoute(KeyboardProfile profile) {
        if (inputView == null
                || profile == null
                || !LanguageRegistry.isTransliterationOnly(profile.id())
                || inputView.isTransliterating()) {
            return;
        }
        inputView.toggleTransliteration();
    }

    private TransliterationEngine boundTransliterationEngine(
            boolean transliterating,
            KeyboardProfile profile
    ) {
        if (!transliterating || transliterationCatalog == null || profile == null) {
            return null;
        }
        return transliterationCatalog.forProfile(profile);
    }

    @Override
    public void onKeyAlternate(KeySpec key, String alternate) {
        InputConnection connection = getCurrentInputConnection();
        if (!inputViewActive || connection == null || inputView == null) {
            return;
        }
        // A variant follows the same reviewed input policy as the key it came from.
        composingSession.appendText(alternate, key.inputPolicy(), null, textSink(connection));
        inputView.consumeOneShotShift();
        refreshSuggestions();
    }

    @Override
    public void onEmojiSelected(String emoji) {
        InputConnection connection = getCurrentInputConnection();
        if (!inputViewActive || connection == null || inputView == null) {
            return;
        }
        // Emoji are literal text: finish any composition first so the commit cannot be
        // absorbed into a pending word.
        TextSink sink = textSink(connection);
        transliterationSession.finish(sink);
        composingSession.commitRaw(sink);
        boolean committed = sink.commitText(emoji);
        if (committed && emojiHistoryAllowed) {
            inputView.recordEmojiUse(emoji);
        }
        refreshSuggestions();
    }

    @Override
    public void onEmojiBackspace() {
        InputConnection connection = getCurrentInputConnection();
        if (!inputViewActive || connection == null || composingSession == null) {
            return;
        }
        invalidateEditorSelection();
        TextSink sink = textSink(connection);
        if (!transliterationSession.deleteLast(sink)) {
            composingSession.delete(sink);
        }
        refreshSuggestions();
    }

    @Override
    public void onProfileSelected(String profileId) {
        if (languagePreferences.requestActive(profileId)) {
            selectProductProfile(languagePreferences.activeProfile());
        }
    }

    @Override
    public void onCandidateSelected(
            SuggestionQuery owner,
            SuggestionCandidate candidate
    ) {
        if (privateField
                || owner == null
                || candidate == null
                || currentSuggestions == null
                || currentSuggestions.status() != SuggestionSnapshot.Status.READY
                || !currentSuggestions.belongsTo(owner)
                || !currentSuggestions.nBestCandidates().contains(candidate)
                || !composingSession.ownsCurrentSuggestionQuery(owner)) {
            return;
        }
        InputConnection connection = getCurrentInputConnection();
        if (connection != null && composingSession.selectCandidate(
                owner,
                candidate,
                textSink(connection)
        )) {
            refreshSuggestions();
        }
    }

    @Override
    public void onSuggestionRetry() {
        if (composingSession != null && composingSession.retrySuggestions()) {
            refreshSuggestions();
        }
    }

    @Override
    public void onManageLanguages() {
        Intent intent = new Intent(this, SettingsActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(intent);
    }

    @Override
    public void onOtherKeyboards() {
        InputMethodManager manager = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
        manager.showInputMethodPicker();
    }

    @Override
    public void onCurrentInputMethodSubtypeChanged(InputMethodSubtype newSubtype) {
        super.onCurrentInputMethodSubtypeChanged(newSubtype);
        if (languagePreferences == null) {
            return;
        }
        KeyboardProfile observed = subtypeRegistry == null
                ? null
                : subtypeRegistry.profileForSubtype(newSubtype);
        reconcileObservedSubtype(observed);
    }

    static String profileIdForSubtypeForTesting(String explicitProfileId, String languageTag) {
        KeyboardProfile explicit = LanguageRegistry.find(explicitProfileId);
        if (explicit != null
                && explicit.isAvailable()
                && languageTag != null
                && languageTag.equalsIgnoreCase(explicit.localeTag())) {
            return explicit.id();
        }
        return null;
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && inputView != null && inputView.hidePicker()) {
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    public void onUpdateSelection(
            int oldSelStart,
            int oldSelEnd,
            int newSelStart,
            int newSelEnd,
            int candidatesStart,
            int candidatesEnd
    ) {
        super.onUpdateSelection(
                oldSelStart,
                oldSelEnd,
                newSelStart,
                newSelEnd,
                candidatesStart,
                candidatesEnd
        );
        updateEditorSelection(newSelStart, newSelEnd);
        boolean caretLeftComposingText =
                newSelStart != candidatesEnd || newSelEnd != candidatesEnd;
        if (transliterationSession.hasComposingText() && caretLeftComposingText) {
            // The caret no longer sits at the end of the phonetic buffer, so the buffer
            // is closed here; otherwise the next keystroke would republish it at the new
            // caret and overwrite unrelated text.
            InputConnection connection = getCurrentInputConnection();
            if (connection != null) {
                transliterationSession.finish(textSink(connection));
            } else {
                transliterationSession.reset();
            }
        }
        if (composingSession == null || !composingSession.hasComposingText()) {
            return;
        }
        if (caretLeftComposingText) {
            InputConnection connection = getCurrentInputConnection();
            if (connection != null) {
                composingSession.finish(textSink(connection));
            } else {
                KeyboardProfile profile = composingSession.profile();
                composingSession.reset(profile, false, privateField);
            }
            refreshSuggestions();
        }
    }

    private void switchProfile(KeyboardProfile profile) {
        KeyboardProfile previous = composingSession.profile();
        boolean changed = previous == null || !previous.id().equals(profile.id());
        EditorInfo editorInfo = getCurrentInputEditorInfo();
        boolean composingAllowed = inputViewActive
                && editorInfo != null
                && EditorMode.from(editorInfo).composingAllowed();
        InputConnection connection = inputViewActive ? getCurrentInputConnection() : null;
        if (changed && connection != null) {
            composingSession.switchProfile(
                    profile,
                    composingAllowed,
                    privateField,
                    textSink(connection)
            );
        } else if (changed) {
            composingSession.reset(profile, composingAllowed, privateField);
        }
        if (changed) {
            // The old profile's Roman buffer belongs to the old script, so it is
            // committed under the engine that produced it before the new one binds.
            if (connection != null) {
                transliterationSession.finish(textSink(connection));
            }
            // Republishing availability first lets the view drop the mode by itself when
            // the incoming profile has no reviewed map, so the toggle cannot stay stuck on.
            if (inputView != null) {
                inputView.setTransliterationAvailable(
                        transliterationCatalog != null
                                && transliterationCatalog.supports(profile)
                );
            }
            forcePhoneticInputWhenItIsTheOnlyRoute(profile);
            transliterationSession.start(
                    boundTransliterationEngine(
                            inputView != null && inputView.isTransliterating(),
                            profile
                    ),
                    privateField
            );
        }
        if (inputView != null) {
            inputView.setProfile(profile);
            inputView.setEditorMode(
                    editorInfo == null ? EditorMode.OTHER : EditorMode.from(editorInfo)
            );
            refreshSuggestions();
        }
    }

    private void selectProductProfile(KeyboardProfile profile) {
        notifyProductProfilePending(profile);
        switchProfile(profile);
        synchronizeEnabledSubtypes();
        requestedSubtypeProfileId = null;
        mismatchedSubtypeCallbacks = 0;
        languageSwitchFailureShown = false;
        requestPendingSubtype(false);
    }

    private KeyboardProfile reconcileCurrentPlatformProfile() {
        KeyboardProfile observed = null;
        if (subtypeRegistry != null) {
            try {
                observed = subtypeRegistry.currentProfile();
            } catch (RuntimeException unavailablePlatformState) {
                subtypeRegistry = null;
            }
        }
        KeyboardProfile desired = languagePreferences.observePlatformProfile(
                observed == null ? null : observed.id()
        );
        notifyPlatformProfileObserved("start_input_view", observed, desired);
        return desired;
    }

    private void reconcileObservedSubtype(KeyboardProfile observed) {
        KeyboardProfile desired = languagePreferences.observePlatformProfile(
                observed == null ? null : observed.id()
        );
        notifyPlatformProfileObserved("subtype_callback", observed, desired);
        switchProfile(desired);
        synchronizeEnabledSubtypes();
        KeyboardProfile pending = languagePreferences.pendingProfile();
        boolean mismatch = pending != null
                && (observed == null || !pending.id().equals(observed.id()));
        requestPendingSubtype(mismatch);
    }

    private void reconcileProductPreferences() {
        if (languagePreferences == null || composingSession == null) {
            return;
        }
        if (inputView != null && keyboardPreferences != null) {
            inputView.applyPreferences(keyboardPreferences);
            updateNavigationBarAppearance();
        }
        switchProfile(languagePreferences.activeProfile());
        synchronizeEnabledSubtypes();
        requestPendingSubtype(false);
    }

    private void synchronizeEnabledSubtypes() {
        if (subtypeRegistry == null || languagePreferences == null) {
            return;
        }
        try {
            subtypeRegistry.synchronizeEnabledProfiles(languagePreferences.enabledProfiles());
        } catch (RuntimeException ignoredPlatformSynchronizationFailure) {
            // The product picker remains authoritative on API 26-33 and literal typing
            // remains available if Android rejects its managed subtype update on 34+.
        }
    }

    private void requestPendingSubtype(boolean callbackMismatch) {
        KeyboardProfile pending = languagePreferences == null
                ? null
                : languagePreferences.pendingProfile();
        if (pending == null) {
            requestedSubtypeProfileId = null;
            mismatchedSubtypeCallbacks = 0;
            languageSwitchFailureShown = false;
            return;
        }
        String profileId = pending.id();
        if (callbackMismatch && profileId.equals(requestedSubtypeProfileId)) {
            if (mismatchedSubtypeCallbacks >= 1) {
                showLanguageSwitchFailure();
                return;
            }
            mismatchedSubtypeCallbacks++;
        } else if (!profileId.equals(requestedSubtypeProfileId)) {
            requestedSubtypeProfileId = profileId;
            mismatchedSubtypeCallbacks = 0;
            languageSwitchFailureShown = false;
        } else if (!callbackMismatch) {
            return;
        }

        if (subtypeRegistry == null) {
            showLanguageSwitchFailure();
            return;
        }
        AndroidSubtypeRegistry.SwitchOutcome outcome = subtypeRegistry.requestSwitch(
                this,
                legacyImeToken(),
                profileId
        );
        notifySwitchDispatched(profileId, outcome);
        if (!outcome.dispatched) {
            showLanguageSwitchFailure();
        }
    }

    static void setSubtypeTransitionObserverForTesting(
            SubtypeTransitionObserver observer
    ) {
        subtypeTransitionObserver = observer;
    }

    boolean privateFieldForTesting() {
        return privateField;
    }

    boolean emojiHistoryAllowedForTesting() {
        return emojiHistoryAllowed;
    }

    boolean inputViewActiveForTesting() {
        return inputViewActive;
    }

    private void notifyInputViewActive() {
        SubtypeTransitionObserver observer = subtypeTransitionObserver;
        if (observer != null) {
            observer.onInputViewActive(this, inputView, legacyImeToken() != null);
        }
    }

    private void notifyProductProfilePending(KeyboardProfile profile) {
        SubtypeTransitionObserver observer = subtypeTransitionObserver;
        if (observer != null) {
            KeyboardProfile pending = languagePreferences.pendingProfile();
            observer.onProductProfilePending(
                    profile.id(),
                    pending == null ? null : pending.id()
            );
        }
    }

    private void notifySwitchDispatched(
            String profileId,
            AndroidSubtypeRegistry.SwitchOutcome outcome
    ) {
        SubtypeTransitionObserver observer = subtypeTransitionObserver;
        if (observer != null) {
            observer.onSwitchDispatched(
                    profileId,
                    outcome.path,
                    outcome.legacyWindowTokenPresent,
                    outcome.dispatched
            );
        }
    }

    private void notifyPlatformProfileObserved(
            String source,
            KeyboardProfile observed,
            KeyboardProfile active
    ) {
        SubtypeTransitionObserver observer = subtypeTransitionObserver;
        if (observer != null) {
            KeyboardProfile pending = languagePreferences.pendingProfile();
            observer.onPlatformProfileObserved(
                    source,
                    observed == null ? null : observed.id(),
                    active == null ? null : active.id(),
                    pending == null ? null : pending.id()
            );
        }
    }

    private IBinder legacyImeToken() {
        if (getWindow() == null || getWindow().getWindow() == null) {
            return null;
        }
        // AOSP assigns the attached IME token to the SoftInputWindow attributes.
        return getWindow().getWindow().getAttributes().token;
    }

    /** Keeps Android's IME navigation controls legible over the active keyboard theme. */
    private void updateNavigationBarAppearance() {
        if (keyboardPreferences == null || getWindow() == null) {
            return;
        }
        Window window = getWindow().getWindow();
        if (window == null) {
            return;
        }
        KeyboardTheme theme = KeyboardTheme.resolve(this, keyboardPreferences.themeId());
        boolean lightSurface = Color.luminance(theme.surfaceColor()) >= 0.5d;
        window.setNavigationBarColor(theme.surfaceColor());
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            WindowInsetsController controller = window.getInsetsController();
            if (controller != null) {
                controller.setSystemBarsAppearance(
                        lightSurface
                                ? WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
                                : 0,
                        WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
                );
            }
        } else {
            View decor = window.getDecorView();
            int flags = decor.getSystemUiVisibility();
            flags = lightSurface
                    ? flags | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
                    : flags & ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            decor.setSystemUiVisibility(flags);
        }
    }

    boolean navigationBarAppearanceMatchesForTesting() {
        if (keyboardPreferences == null || getWindow() == null) {
            return false;
        }
        Window window = getWindow().getWindow();
        if (window == null) {
            return false;
        }
        boolean expectedLight = Color.luminance(
                KeyboardTheme.resolve(this, keyboardPreferences.themeId()).surfaceColor()
        ) >= 0.5d;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            WindowInsetsController controller = window.getInsetsController();
            return controller != null
                    && ((controller.getSystemBarsAppearance()
                    & WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS) != 0)
                    == expectedLight;
        }
        return ((window.getDecorView().getSystemUiVisibility()
                & View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR) != 0) == expectedLight;
    }

    private void showLanguageSwitchFailure() {
        if (languageSwitchFailureShown) {
            return;
        }
        languageSwitchFailureShown = true;
        Toast.makeText(this, R.string.language_switch_failed, Toast.LENGTH_SHORT).show();
    }

    private void refreshSuggestions() {
        cancelSuggestionDeadline();
        if (composingSession == null || suggestionEngine == null || destroyed) {
            publishSuggestions(null);
            return;
        }
        // Suppressing the strip must also stop dispatching queries, so a disabled
        // preference cannot leak typed context into a suggestion request.
        if (keyboardPreferences != null && !keyboardPreferences.suggestionsEnabled()) {
            composingSession.cancelSuggestions();
            currentSuggestions = null;
            publishSuggestions(null);
            return;
        }
        SuggestionDispatch dispatch = composingSession.beginSuggestionDispatch();
        currentSuggestions = dispatch.immediateSnapshot();
        publishSuggestions(currentSuggestions);
        SuggestionQuery query = dispatch.query();
        if (query == null) {
            return;
        }
        dispatchedSuggestionQuery = query;
        SuggestionEngine.SubmitOutcome outcome = suggestionEngine.submit(
                query,
                (completedQuery, snapshot) -> {
                    Handler handler = mainHandler;
                    if (handler != null) {
                        handler.post(() -> onSuggestionResult(completedQuery, snapshot));
                    }
                }
        );
        if (outcome == SuggestionEngine.SubmitOutcome.ACCEPTED) {
            scheduleSuggestionDeadline(query);
        } else {
            dispatchedSuggestionQuery = null;
        }
    }

    private void onSuggestionResult(
            SuggestionQuery query,
            SuggestionSnapshot snapshot
    ) {
        if (destroyed
                || !inputViewActive
                || query == null
                || query != dispatchedSuggestionQuery) {
            return;
        }
        cancelSuggestionDeadline();
        if (composingSession.acceptSuggestionResult(query, snapshot)) {
            publishSuggestions(composingSession.currentSuggestionSnapshot());
        } else if (composingSession.ownsCurrentSuggestionQuery(query)) {
            publishSuggestions(composingSession.currentSuggestionSnapshot());
        }
    }

    private void scheduleSuggestionDeadline(SuggestionQuery query) {
        long remainingNanos = query.deadlineNanos() - System.nanoTime();
        if (remainingNanos <= 0L) {
            onSuggestionDeadline(query);
            return;
        }
        long delayMillis = Math.max(1L, (remainingNanos + 999_999L) / 1_000_000L);
        Runnable callback = () -> onSuggestionDeadline(query);
        suggestionDeadlineCallback = callback;
        mainHandler.postDelayed(callback, delayMillis);
    }

    private void onSuggestionDeadline(SuggestionQuery query) {
        if (destroyed || query != dispatchedSuggestionQuery) {
            return;
        }
        if (!query.isExpired(System.nanoTime())) {
            scheduleSuggestionDeadline(query);
            return;
        }
        suggestionDeadlineCallback = null;
        dispatchedSuggestionQuery = null;
        if (composingSession.expireSuggestionQuery(query)) {
            publishSuggestions(composingSession.currentSuggestionSnapshot());
        }
    }

    private void cancelSuggestionDeadline() {
        Runnable callback = suggestionDeadlineCallback;
        suggestionDeadlineCallback = null;
        dispatchedSuggestionQuery = null;
        if (mainHandler != null && callback != null) {
            mainHandler.removeCallbacks(callback);
        }
    }

    private InputConnectionTextSink textSink(InputConnection connection) {
        return new InputConnectionTextSink(
                connection,
                !privateField,
                editorSelectionStart,
                editorSelectionEnd
        );
    }

    private void invalidateEditorSelection() {
        editorSelectionStart = -1;
        editorSelectionEnd = -1;
    }

    private void updateEditorSelection(int selectionStart, int selectionEnd) {
        if (selectionStart < 0 || selectionEnd < 0) {
            editorSelectionStart = -1;
            editorSelectionEnd = -1;
            return;
        }
        editorSelectionStart = selectionStart;
        editorSelectionEnd = selectionEnd;
    }

    private void cancelDeleteRepeat() {
        if (inputView != null) {
            inputView.cancelDeleteRepeat();
        }
    }

    private void publishSuggestions(SuggestionSnapshot snapshot) {
        currentSuggestions = snapshot;
        if (inputView == null) {
            return;
        }
        if (snapshot == null) {
            inputView.clearSuggestions();
        } else {
            inputView.setSuggestionSnapshot(snapshot);
        }
    }

    private void onSuggestionStateChanged(SuggestionActivation activation) {
        if (destroyed
                || composingSession == null
                || !composingSession.hasComposingText()
                || !composingSession.ownsActivation(activation)) {
            return;
        }
        refreshSuggestions();
    }

    private void performEnter(InputConnection connection) {
        EditorInfo info = getCurrentInputEditorInfo();
        int action = info == null
                ? EditorInfo.IME_ACTION_NONE
                : info.imeOptions & EditorInfo.IME_MASK_ACTION;
        if (action != EditorInfo.IME_ACTION_NONE && action != EditorInfo.IME_ACTION_UNSPECIFIED) {
            connection.performEditorAction(action);
        } else {
            connection.commitText("\n", 1);
        }
    }

}
