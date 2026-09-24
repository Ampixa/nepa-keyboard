package com.ampixa.nepakeyboard.ime;

import android.annotation.SuppressLint;
import android.content.Context;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.text.TextUtils;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.BaseAdapter;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Keyboard chrome: candidate strip, keyboard surface, and in-window language sheet. */
@SuppressLint("ViewConstructor")
public final class NepaInputView extends FrameLayout {
    public interface Listener {
        void onKey(KeySpec key, SpatialKeyStroke stroke);

        void onProfileSelected(String profileId);

        void onCandidateSelected(
                SuggestionQuery owner,
                SuggestionCandidate candidate
        );

        void onSuggestionRetry();

        void onManageLanguages();

        void onOtherKeyboards();

        /**
         * An emoji cell was chosen; the service owns committing it. Rendering and
         * dispatch harnesses have no editor, so they inherit a no-op.
         */
        default void onEmojiSelected(String emoji) {
        }

        /** Backspace was pressed while the emoji panel was open. */
        default void onEmojiBackspace() {
        }

        /** A long-press variant was chosen for a text key. */
        default void onKeyAlternate(KeySpec key, String alternate) {
        }

        /** Phonetic input was switched on or off. */
        default void onTransliterationModeChanged(boolean transliterating) {
        }
    }

    private final Listener listener;
    private final LinearLayout keyboardContent;
    private final LinearLayout toolbarStrip;
    private final KeyboardSurface keyboardSurface;
    private final TextView profileChip;
    private final TextView settingsChip;
    private final TextView[] candidateViews = new TextView[3];
    private final Typeface[] candidateDefaultTypefaces = new Typeface[3];
    private final SuggestionCandidate[] candidateBindings = new SuggestionCandidate[3];
    private SuggestionQuery candidateOwner;
    private final SuggestionCandidateRow candidateRow;
    private final LinearLayout suggestionStatusRow;
    private final TextView suggestionStatusText;
    private final TextView suggestionStatusAction;
    private final LinearLayout pickerSheet;
    private final KeyPreviewOverlay keyPreviewOverlay;
    private final TextView emojiChip;
    private final TextView translitChip;
    private final EmojiPanel emojiPanel;
    private EmojiCatalog emojiCatalog;
    private KeyAlternatesCatalog keyAlternates;
    private KeyboardPreferences keyboardPreferences;
    private KeyboardTheme activeTheme;
    private int toolbarIconTintColor;
    private boolean transliterationAvailable;
    private boolean emojiHistoryAllowed = true;
    private final int surfaceColor;
    private final int textColor;
    private final int secondaryTextColor;
    private final ScriptTypefaceRegistry scriptTypefaces;
    private KeyboardProfile profile;
    private KeyboardUiState uiState;
    private boolean keyPreviewEnabled = KeyboardPreferences.DEFAULT_KEY_PREVIEW_ENABLED;
    private ListView pickerProfileList;
    private PickerProfileAdapter pickerProfileAdapter;
    private View pickerInitialFocus;
    private View pickerReturnFocus;
    private boolean pickerAccessibilityModal;
    private boolean pickerReturnHadInputFocus;
    private int keyboardContentVisibility;
    private int keyboardContentAccessibilityImportance;
    private int pickerSheetAccessibilityImportance;
    private int pickerAccessibilityGeneration;
    private SuggestionSnapshot.Status displayedSuggestionStatus =
            SuggestionSnapshot.Status.INACTIVE;

    public NepaInputView(Context context, Listener listener) {
        super(context);
        this.listener = listener;
        boolean dark = (context.getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        surfaceColor = dark ? Color.rgb(30, 29, 34) : Color.rgb(246, 245, 250);
        textColor = dark ? Color.rgb(245, 243, 248) : Color.rgb(34, 32, 38);
        secondaryTextColor = dark ? Color.rgb(196, 191, 203) : Color.rgb(91, 87, 99);
        scriptTypefaces = new ScriptTypefaceRegistry(context);
        setBackgroundColor(surfaceColor);

        keyboardContent = new LinearLayout(context);
        keyboardContent.setOrientation(LinearLayout.VERTICAL);
        keyboardContent.setPadding(dp(4), dp(4), dp(4), dp(4));
        addView(keyboardContent, new FrameLayout.LayoutParams(
                LayoutParams.MATCH_PARENT,
                LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM
        ));

        toolbarStrip = new LinearLayout(context);
        toolbarStrip.setOrientation(LinearLayout.HORIZONTAL);
        toolbarStrip.setGravity(Gravity.CENTER_VERTICAL);
        toolbarStrip.setPadding(dp(4), dp(3), dp(4), dp(3));
        keyboardContent.addView(
                toolbarStrip,
                new LinearLayout.LayoutParams(LayoutParams.MATCH_PARENT, dp(54))
        );

        profileChip = toolbarButton("", getContext().getString(R.string.switch_language));
        applyToolbarIcon(profileChip, R.drawable.ic_language_switch_24);
        profileChip.setOnClickListener(this::showLanguagePicker);
        LinearLayout.LayoutParams profileChipParams = new LinearLayout.LayoutParams(
                dp(48),
                dp(48)
        );
        profileChipParams.setMarginEnd(dp(2));
        toolbarStrip.addView(profileChip, profileChipParams);

        FrameLayout suggestionArea = new FrameLayout(context);
        toolbarStrip.addView(suggestionArea, new LinearLayout.LayoutParams(0, dp(48), 1f));

        candidateRow = new SuggestionCandidateRow();
        candidateRow.setOrientation(LinearLayout.HORIZONTAL);
        candidateRow.setAccessibilityLiveRegion(ACCESSIBILITY_LIVE_REGION_NONE);
        suggestionArea.addView(candidateRow, new FrameLayout.LayoutParams(
                LayoutParams.MATCH_PARENT,
                LayoutParams.MATCH_PARENT
        ));
        for (int index = 0; index < candidateViews.length; index++) {
            TextView candidate = toolbarButton(
                    "",
                    getContext().getString(R.string.suggestion_number, index + 1)
            );
            candidate.setVisibility(INVISIBLE);
            final int candidateIndex = index;
            candidate.setOnClickListener(view -> {
                SuggestionCandidate binding = candidateBindings[candidateIndex];
                if (binding != null) {
                    listener.onCandidateSelected(candidateOwner, binding);
                }
            });
            candidateDefaultTypefaces[index] = candidate.getTypeface();
            candidateViews[index] = candidate;
            candidateRow.addView(candidate, new LinearLayout.LayoutParams(0, dp(48), 1f));
        }

        suggestionStatusRow = new LinearLayout(context);
        suggestionStatusRow.setOrientation(LinearLayout.HORIZONTAL);
        suggestionStatusRow.setGravity(Gravity.CENTER_VERTICAL);
        suggestionStatusRow.setAccessibilityLiveRegion(ACCESSIBILITY_LIVE_REGION_POLITE);
        suggestionStatusRow.setVisibility(INVISIBLE);
        suggestionStatusText = textView("", 14, secondaryTextColor);
        suggestionStatusText.setGravity(Gravity.CENTER_VERTICAL);
        suggestionStatusText.setMaxLines(2);
        suggestionStatusText.setEllipsize(TextUtils.TruncateAt.END);
        suggestionStatusRow.addView(suggestionStatusText, new LinearLayout.LayoutParams(
                0,
                LayoutParams.MATCH_PARENT,
                1f
        ));
        suggestionStatusAction = toolbarButton("", "");
        suggestionStatusAction.setVisibility(GONE);
        suggestionStatusAction.setOnClickListener(view -> {
            if (displayedSuggestionStatus == SuggestionSnapshot.Status.UNAVAILABLE) {
                listener.onSuggestionRetry();
            } else if (displayedSuggestionStatus == SuggestionSnapshot.Status.MISSING
                    || displayedSuggestionStatus == SuggestionSnapshot.Status.CORRUPT) {
                showLanguagePicker(view);
            }
        });
        suggestionStatusRow.addView(suggestionStatusAction, new LinearLayout.LayoutParams(
                LayoutParams.WRAP_CONTENT,
                dp(48)
        ));
        suggestionArea.addView(suggestionStatusRow, new FrameLayout.LayoutParams(
                LayoutParams.MATCH_PARENT,
                LayoutParams.MATCH_PARENT
        ));

        translitChip = toolbarButton(
                getContext().getString(R.string.phonetic_input_symbol),
                getContext().getString(R.string.phonetic_input)
        );
        translitChip.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        translitChip.setOnClickListener(view -> toggleTransliteration());
        translitChip.setVisibility(GONE);
        LinearLayout.LayoutParams translitParams = new LinearLayout.LayoutParams(dp(48), dp(48));
        translitParams.setMarginStart(dp(2));
        toolbarStrip.addView(translitChip, translitParams);

        emojiChip = toolbarButton("☺", getContext().getString(R.string.emoji_title));
        emojiChip.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        emojiChip.setOnClickListener(view -> toggleEmojiPanel());
        LinearLayout.LayoutParams emojiParams = new LinearLayout.LayoutParams(dp(48), dp(48));
        emojiParams.setMarginStart(dp(2));
        toolbarStrip.addView(emojiChip, emojiParams);

        settingsChip = toolbarButton("", getContext().getString(R.string.settings));
        applyToolbarIcon(settingsChip, R.drawable.ic_settings_24);
        settingsChip.setOnClickListener(view -> listener.onManageLanguages());
        LinearLayout.LayoutParams settingsParams = new LinearLayout.LayoutParams(dp(48), dp(48));
        settingsParams.setMarginStart(dp(2));
        toolbarStrip.addView(settingsChip, settingsParams);

        keyPreviewOverlay = new KeyPreviewOverlay(context);
        keyPreviewOverlay.setAlternateListener(
                (key, alternate) -> listener.onKeyAlternate(key, alternate)
        );

        keyboardSurface = new KeyboardSurface(context);
        keyboardSurface.setListener(new KeyboardSurface.Listener() {
            @Override
            public void onKey(KeySpec key, SpatialKeyStroke stroke) {
                listener.onKey(key, stroke);
            }

            @Override
            public void onLanguagePickerRequested(View source) {
                showLanguagePicker(source);
            }

            @Override
            public void onKeyPressed(KeySpec key, View keyView) {
                if (keyPreviewEnabled) {
                    keyPreviewOverlay.show(key, keyView);
                }
            }

            @Override
            public void onKeyReleased() {
                keyPreviewOverlay.hide();
            }

            @Override
            public boolean onKeyAlternatesRequested(KeySpec key, View keyView) {
                return keyPreviewOverlay.showAlternates(key, keyView);
            }

            @Override
            public void onKeyAlternateDrag(float windowX) {
                keyPreviewOverlay.moveAlternateSelection(windowX);
            }

            @Override
            public boolean onKeyAlternateCommit() {
                return keyPreviewOverlay.commitHighlightedAlternate();
            }

            @Override
            public void onKeyAlternateSelected(KeySpec key, String alternate) {
                keyPreviewOverlay.hide();
                listener.onKeyAlternate(key, alternate);
            }
        });
        keyboardContent.addView(keyboardSurface, new LinearLayout.LayoutParams(
                LayoutParams.MATCH_PARENT,
                LayoutParams.WRAP_CONTENT
        ));

        emojiPanel = new EmojiPanel(context, new EmojiPanel.Listener() {
            @Override
            public void onEmojiSelected(String emoji) {
                listener.onEmojiSelected(emoji);
            }

            @Override
            public void onEmojiBackspace() {
                listener.onEmojiBackspace();
            }

            @Override
            public void onEmojiDismissed() {
                showLetters();
            }
        });
        emojiPanel.setVisibility(GONE);
        keyboardContent.addView(emojiPanel, new LinearLayout.LayoutParams(
                LayoutParams.MATCH_PARENT,
                LayoutParams.WRAP_CONTENT
        ));

        pickerSheet = new LinearLayout(context);
        pickerSheet.setOrientation(LinearLayout.VERTICAL);
        pickerSheet.setPadding(dp(16), dp(12), dp(16), dp(12));
        pickerSheet.setBackgroundColor(surfaceColor);
        pickerSheet.setClickable(true);
        pickerSheet.setFocusable(true);
        pickerSheet.setVisibility(GONE);
        addView(pickerSheet, new FrameLayout.LayoutParams(
                LayoutParams.MATCH_PARENT,
                LayoutParams.MATCH_PARENT,
                Gravity.BOTTOM
        ));

        // Added last so a preview always draws above the keys it describes.
        addView(keyPreviewOverlay, new FrameLayout.LayoutParams(
                LayoutParams.MATCH_PARENT,
                LayoutParams.MATCH_PARENT
        ));

        // A newly attached input view must already have complete chrome styling.
        // Saved preferences may replace this immediately, but leaving activeTheme
        // null made selected toolbar controls visually transparent during startup.
        applyTheme(KeyboardTheme.resolve(getContext(), KeyboardTheme.SYSTEM_ID));
    }

    public void setProfile(KeyboardProfile profile) {
        if (pickerSheet.getVisibility() == VISIBLE || pickerAccessibilityModal) {
            closeLanguagePicker(true, true);
        }
        this.profile = profile;
        clearSuggestions();
        uiState = uiState == null
                ? KeyboardUiState.initial(profile.id())
                : KeyboardUiReducer.onProfileSelected(uiState, profile.id());
        profileChip.setContentDescription(getContext().getString(
                R.string.current_language_description,
                profile.displayName()
        ));
        renderKeyboard();
    }

    void cancelDeleteRepeat() {
        keyboardSurface.cancelDeleteRepeat();
        keyPreviewOverlay.hide();
    }

    /** Applies every reviewed shell preference in one pass. */
    public void applyPreferences(KeyboardPreferences preferences) {
        keyboardPreferences = preferences;
        keyPreviewEnabled = preferences.keyPreviewEnabled();
        if (!keyPreviewEnabled) {
            keyPreviewOverlay.hide();
        }
        keyboardSurface.setFeedbackEnabled(
                preferences.soundEnabled(),
                preferences.hapticsEnabled()
        );
        keyboardSurface.setHeightPercent(preferences.heightPercent());
        applyTheme(KeyboardTheme.resolve(getContext(), preferences.themeId()));
    }

    /** Applies a bundled theme to the chrome and the key surface together. */
    public void applyTheme(KeyboardTheme theme) {
        activeTheme = theme;
        setBackgroundColor(theme.surfaceColor());
        pickerSheet.setBackgroundColor(theme.surfaceColor());
        profileChip.setTextColor(theme.textColor());
        settingsChip.setTextColor(theme.textColor());
        emojiChip.setTextColor(theme.textColor());
        translitChip.setTextColor(theme.textColor());
        tintToolbarIcon(profileChip, theme.textColor());
        tintToolbarIcon(settingsChip, theme.textColor());
        suggestionStatusText.setTextColor(theme.secondaryTextColor());
        suggestionStatusAction.setTextColor(theme.textColor());
        for (TextView candidate : candidateViews) {
            candidate.setTextColor(theme.textColor());
        }
        keyboardSurface.setTheme(theme);
        emojiPanel.setTheme(theme);
        updateToolbarToggleStates();
    }

    KeyboardTheme activeThemeForTesting() {
        return activeTheme;
    }

    boolean keyPreviewEnabledForTesting() {
        return keyPreviewEnabled;
    }

    boolean keyPreviewShowingForTesting() {
        return keyPreviewOverlay.isShowing();
    }

    String keyPreviewKeyIdForTesting() {
        return keyPreviewOverlay.shownKeyIdForTesting();
    }

    KeyboardMetrics keyboardMetricsForTesting() {
        return keyboardSurface.metrics();
    }

    KeyboardSurface keyboardSurfaceForTesting() {
        return keyboardSurface;
    }

    KeyPreviewOverlay keyPreviewOverlayForTesting() {
        return keyPreviewOverlay;
    }

    public KeyboardProfile profile() {
        return profile;
    }

    /** Applies the classified editor, which owns the panel a new input starts on. */
    public void setEditorMode(EditorMode editorMode) {
        if (uiState == null) {
            return;
        }
        uiState = KeyboardUiReducer.onStartInput(uiState, uiState.profileId(), editorMode);
        renderKeyboard();
    }

    /** Keeps recent emoji out of editors that disallow personalized learning. */
    public void setEmojiHistoryAllowed(boolean allowed) {
        emojiHistoryAllowed = allowed;
        emojiPanel.updateRecents(allowed && keyboardPreferences != null
                ? keyboardPreferences.recentEmoji() : Collections.emptyList());
    }

    public void setNumeric(boolean numeric) {
        setEditorMode(numeric ? EditorMode.NUMBER : EditorMode.TEXT);
    }

    public void setShifted(boolean shifted) {
        if (uiState == null) {
            return;
        }
        uiState = KeyboardUiReducer.onShiftSet(uiState, shifted);
        renderKeyboard();
    }

    /** Cycles shift off, one-shot, and locked using the reviewed double-tap window. */
    public void toggleShift(long nowMillis) {
        if (uiState == null) {
            return;
        }
        uiState = KeyboardUiReducer.onShiftTapped(uiState, nowMillis);
        renderKeyboard();
    }

    /** Consumes a one-shot shift after committed text without releasing caps lock. */
    public void consumeOneShotShift() {
        if (uiState == null) {
            return;
        }
        KeyboardUiState next = KeyboardUiReducer.onTextCommitted(uiState);
        if (next.equals(uiState)) {
            return;
        }
        uiState = next;
        renderKeyboard();
    }

    public boolean isShifted() {
        return uiState != null && uiState.rendersShiftLayer();
    }

    public boolean isCapsLocked() {
        return uiState != null
                && uiState.shiftState() == KeyboardUiState.ShiftState.LOCKED;
    }

    public KeyboardUiState uiState() {
        return uiState;
    }

    public void showSymbols() {
        if (uiState == null) {
            return;
        }
        uiState = KeyboardUiReducer.onSymbolsRequested(uiState);
        renderKeyboard();
    }

    public void showLetters() {
        if (uiState == null) {
            return;
        }
        uiState = KeyboardUiReducer.onLettersRequested(uiState);
        renderKeyboard();
    }

    /** Switches between typing the script directly and typing it phonetically. */
    public void toggleTransliteration() {
        if (uiState == null || !transliterationAvailable) {
            return;
        }
        uiState = KeyboardUiReducer.onTransliterationToggled(uiState);
        listener.onTransliterationModeChanged(uiState.transliterating());
        renderKeyboard();
    }

    /** Declares whether the active profile can be typed phonetically. */
    public void setTransliterationAvailable(boolean available) {
        transliterationAvailable = available;
        translitChip.setVisibility(available ? VISIBLE : GONE);
        if (!available && uiState != null && uiState.transliterating()) {
            uiState = KeyboardUiReducer.onTransliterationToggled(uiState);
            listener.onTransliterationModeChanged(false);
            renderKeyboard();
        }
    }

    public boolean isTransliterating() {
        return uiState != null && uiState.transliterating();
    }

    /** Opens the emoji panel, or returns to keys when it is already open. */
    public void toggleEmojiPanel() {
        if (uiState == null) {
            return;
        }
        if (uiState.panel() == KeyboardUiState.Panel.EMOJI) {
            showLetters();
            return;
        }
        uiState = KeyboardUiReducer.onEmojiRequested(uiState);
        renderKeyboard();
    }

    public boolean emojiPanelVisible() {
        return emojiPanel.getVisibility() == VISIBLE;
    }

    /** Records the selection so the recents page reflects it immediately. */
    public void recordEmojiUse(String emoji) {
        if (!emojiHistoryAllowed || keyboardPreferences == null) {
            return;
        }
        keyboardPreferences.recordRecentEmoji(emoji);
        emojiPanel.updateRecents(keyboardPreferences.recentEmoji());
    }

    EmojiPanel emojiPanelForTesting() {
        return emojiPanel;
    }

    public void setSuggestionSnapshot(SuggestionSnapshot snapshot) {
        if (snapshot == null
                || profile == null
                || !snapshot.activation().isActive()
                || !profile.id().equals(snapshot.activation().profileId())) {
            clearSuggestions();
            return;
        }
        displayedSuggestionStatus = snapshot.status();
        if (snapshot.status() == SuggestionSnapshot.Status.READY) {
            renderCandidates(snapshot);
            return;
        }
        clearCandidateViews();
        switch (snapshot.status()) {
            case LOADING:
                showSuggestionStatus(R.string.loading_suggestions, 0, 0);
                return;
            case NO_MATCH:
                showSuggestionStatus(R.string.no_dictionary_suggestions, 0, 0);
                return;
            case MISSING:
                showSuggestionStatus(
                        R.string.dictionary_suggestions_unavailable,
                        R.string.choose_language,
                        R.string.choose_language
                );
                return;
            case CORRUPT:
                showSuggestionStatus(
                        R.string.suggestions_could_not_be_verified,
                        R.string.choose_language,
                        R.string.choose_language
                );
                return;
            case UNAVAILABLE:
                showSuggestionStatus(
                        R.string.suggestions_temporarily_unavailable,
                        R.string.retry,
                        R.string.retry_suggestions
                );
                return;
            case INACTIVE:
            default:
                clearSuggestions();
        }
    }

    public void clearSuggestions() {
        displayedSuggestionStatus = SuggestionSnapshot.Status.INACTIVE;
        suggestionStatusRow.setVisibility(INVISIBLE);
        clearCandidateViews();
        suggestionStatusText.setText("");
        suggestionStatusAction.setText("");
        suggestionStatusAction.setContentDescription(null);
        suggestionStatusAction.setVisibility(GONE);
    }

    private void renderCandidates(SuggestionSnapshot snapshot) {
        List<SuggestionCandidate> values = snapshot.nBestCandidates();
        candidateOwner = snapshot.query();
        displayedSuggestionStatus = values.isEmpty()
                ? SuggestionSnapshot.Status.NO_MATCH
                : SuggestionSnapshot.Status.READY;
        suggestionStatusRow.setVisibility(INVISIBLE);
        candidateRow.setVisibility(VISIBLE);
        for (int index = 0; index < candidateViews.length; index++) {
            TextView candidate = candidateViews[index];
            if (index < values.size() && !values.get(index).text().isEmpty()) {
                SuggestionCandidate binding = values.get(index);
                candidateBindings[index] = binding;
                candidate.setText(binding.text());
                scriptTypefaces.apply(
                        candidate,
                        binding.text(),
                        candidateDefaultTypefaces[index]
                );
                candidate.setContentDescription(getContext().getString(
                        R.string.suggestion_description,
                        binding.text()
                ));
                candidate.setVisibility(VISIBLE);
            } else {
                candidateBindings[index] = null;
                candidate.setText("");
                candidate.setTypeface(candidateDefaultTypefaces[index]);
                candidate.setContentDescription(null);
                candidate.setVisibility(INVISIBLE);
            }
        }
    }

    private void clearCandidateViews() {
        candidateOwner = null;
        candidateRow.setVisibility(INVISIBLE);
        for (int index = 0; index < candidateViews.length; index++) {
            candidateBindings[index] = null;
            TextView candidate = candidateViews[index];
            candidate.setText("");
            candidate.setTypeface(candidateDefaultTypefaces[index]);
            candidate.setContentDescription(null);
            candidate.setVisibility(INVISIBLE);
        }
    }

    private void showSuggestionStatus(
            int messageResource,
            int actionResource,
        int actionDescriptionResource
    ) {
        suggestionStatusText.setText(messageResource);
        if (actionResource == 0) {
            suggestionStatusAction.setText("");
            suggestionStatusAction.setContentDescription(null);
            suggestionStatusAction.setVisibility(GONE);
        } else {
            suggestionStatusAction.setText(actionResource);
            suggestionStatusAction.setContentDescription(
                    getContext().getString(actionDescriptionResource)
            );
            suggestionStatusAction.setVisibility(VISIBLE);
        }
        suggestionStatusRow.setVisibility(VISIBLE);
    }

    public void showLanguagePicker() {
        showLanguagePicker(profileChip);
    }

    private void showLanguagePicker(View returnFocus) {
        if (profile == null || pickerSheet.getVisibility() == VISIBLE) {
            return;
        }
        keyPreviewOverlay.hide();
        pickerSheet.removeAllViews();

        LinearLayout header = new LinearLayout(getContext());
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        TextView title = textView(
                getContext().getString(R.string.choose_language),
                20,
                currentThemeTextColor()
        );
        title.setPadding(dp(8), dp(4), dp(8), dp(10));
        title.setMinHeight(dp(48));
        title.setFocusable(true);
        title.setFocusableInTouchMode(true);
        title.setContentDescription(getContext().getString(R.string.choose_language));
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            title.setAccessibilityHeading(true);
        }
        header.addView(title, new LinearLayout.LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f));

        TextView close = pickerButton("×", getContext().getString(R.string.close_language_picker));
        close.setGravity(Gravity.CENTER);
        close.setTextSize(TypedValue.COMPLEX_UNIT_SP, 24);
        close.setOnClickListener(view -> closeLanguagePicker());
        header.addView(close, pickerActionParams(dp(52), 0f));
        pickerSheet.addView(header, new LinearLayout.LayoutParams(
                LayoutParams.MATCH_PARENT,
                LayoutParams.WRAP_CONTENT
        ));

        pickerProfileList = new ListView(getContext());
        pickerProfileList.setContentDescription(
                getContext().getString(R.string.enabled_language_profiles)
        );
        LanguagePreferences preferences = new LanguagePreferences(getContext());
        pickerProfileAdapter = new PickerProfileAdapter(preferences.enabledProfiles());
        pickerProfileList.setAdapter(pickerProfileAdapter);
        int activePosition = pickerProfileAdapter.positionOf(profile.id());
        if (activePosition >= 0) {
            pickerProfileList.setSelection(activePosition);
        }
        pickerProfileList.setDivider(new ColorDrawable(Color.TRANSPARENT));
        pickerProfileList.setDividerHeight(dp(6));
        pickerProfileList.setPadding(0, dp(3), 0, dp(3));
        pickerProfileList.setClipToPadding(false);
        pickerSheet.addView(pickerProfileList, new LinearLayout.LayoutParams(
                LayoutParams.MATCH_PARENT,
                0,
                1f
        ));

        LinearLayout actions = new LinearLayout(getContext());
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setGravity(Gravity.CENTER_VERTICAL);
        String manageLabel = getContext().getString(R.string.manage_languages);
        TextView manage = pickerButton("＋  " + manageLabel, manageLabel);
        manage.setOnClickListener(view -> {
            closeLanguagePicker(false, false);
            listener.onManageLanguages();
        });
        actions.addView(manage, pickerActionParams(0, 1f));

        String otherLabel = getContext().getString(R.string.other_keyboards);
        TextView others = pickerButton("⌨  " + otherLabel, otherLabel);
        others.setOnClickListener(view -> {
            closeLanguagePicker(false, false);
            listener.onOtherKeyboards();
        });
        actions.addView(others, pickerActionParams(0, 1f));
        pickerSheet.addView(actions, new LinearLayout.LayoutParams(
                LayoutParams.MATCH_PARENT,
                LayoutParams.WRAP_CONTENT
        ));
        pickerSheet.setVisibility(VISIBLE);
        pickerSheet.bringToFront();
        enterPickerAccessibility(title, returnFocus);
    }

    public boolean hidePicker() {
        if (pickerSheet.getVisibility() == VISIBLE) {
            closeLanguagePicker();
            return true;
        }
        return false;
    }

    int renderedRowCountForTesting() {
        return keyboardSurface.getChildCount();
    }

    boolean visualGeometryContractForTesting() {
        Drawable profileIcon = profileChip.getCompoundDrawables()[0];
        return getWidth() > 0
                && getHeight() > 0
                && keyboardContent.getTop() >= 0
                && keyboardContent.getBottom() <= getHeight()
                && keyboardContent.getTop() <= dp(4)
                && getHeight() - keyboardContent.getBottom() <= dp(4)
                && keyboardContent.getPaddingLeft() >= dp(4)
                && keyboardContent.getPaddingRight() >= dp(4)
                && keyboardContent.getPaddingTop() >= dp(4)
                && keyboardContent.getPaddingBottom() >= dp(4)
                && toolbarStrip.getHeight() == dp(54)
                && profileChip.getWidth() == dp(48)
                && TextUtils.isEmpty(profileChip.getText())
                && profileIcon != null
                && keyboardSurface.visualGeometryContractForTesting();
    }

    int actionRowIndexForTesting(KeySpec.Action action) {
        return keyboardSurface.actionRowIndexForTesting(action);
    }

    boolean performTextKeyForTesting(String text) {
        return keyboardSurface.performTextKeyForTesting(text);
    }

    boolean performTextKeyTouchForTesting(
            String text,
            float horizontalFraction,
            float verticalFraction
    ) {
        return keyboardSurface.performTextKeyTouchForTesting(
                text,
                horizontalFraction,
                verticalFraction
        );
    }

    boolean performKeyIdForTesting(String keyId) {
        return keyboardSurface.performKeyIdForTesting(keyId);
    }

    boolean beginDeleteTouchForTesting() {
        return keyboardSurface.beginActionKeyTouchForTesting(KeySpec.Action.DELETE);
    }

    boolean finishDeleteTouchForTesting(boolean cancel) {
        return keyboardSurface.finishActionKeyTouchForTesting(KeySpec.Action.DELETE, cancel);
    }

    boolean deleteRepeatActiveForTesting() {
        return keyboardSurface.deleteRepeatActiveForTesting();
    }

    long deleteDispatchCountForTesting() {
        return keyboardSurface.deleteDispatchCountForTesting();
    }

    boolean pickerHoldAccessibilityActionMatchesForTesting(
            String keyId,
            CharSequence expectedLabel
    ) {
        return keyboardSurface.pickerHoldAccessibilityActionMatchesForTesting(
                keyId,
                expectedLabel
        );
    }

    boolean longClickAccessibilityActionAbsentForTesting(String keyId) {
        return keyboardSurface.longClickAccessibilityActionAbsentForTesting(keyId);
    }

    CharSequence keyContentDescriptionForTesting(String keyId) {
        return keyboardSurface.keyContentDescriptionForTesting(keyId);
    }

    boolean performPickerHoldAccessibilityActionForTesting(String keyId) {
        return keyboardSurface.performPickerHoldAccessibilityActionForTesting(keyId);
    }

    boolean requestKeyInputFocusForTesting(String keyId) {
        return keyboardSurface.requestKeyInputFocusForTesting(keyId);
    }

    boolean keyHasInputFocusForTesting(String keyId) {
        return keyboardSurface.keyHasInputFocusForTesting(keyId);
    }

    boolean clearKeyInputFocusForTesting(String keyId) {
        return keyboardSurface.clearKeyInputFocusForTesting(keyId);
    }

    boolean pickerVisibleForTesting() {
        return pickerSheet.getVisibility() == VISIBLE;
    }

    int pickerChildCountForTesting() {
        int fixedControls = 0;
        if (pickerSheet.getChildCount() > 0
                && pickerSheet.getChildAt(0) instanceof LinearLayout) {
            fixedControls += ((LinearLayout) pickerSheet.getChildAt(0)).getChildCount();
        }
        if (pickerSheet.getChildCount() > 2
                && pickerSheet.getChildAt(2) instanceof LinearLayout) {
            fixedControls += ((LinearLayout) pickerSheet.getChildAt(2)).getChildCount();
        }
        return pickerProfileCountForTesting() + fixedControls;
    }

    int pickerProfileCountForTesting() {
        return pickerProfileAdapter == null ? 0 : pickerProfileAdapter.getCount();
    }

    int pickerAttachedProfileCountForTesting() {
        return pickerProfileList == null ? 0 : pickerProfileList.getChildCount();
    }

    int pickerFirstVisiblePositionForTesting() {
        return pickerProfileList == null ? -1 : pickerProfileList.getFirstVisiblePosition();
    }

    List<View> pickerAttachedRowsForTesting() {
        if (pickerProfileList == null) {
            return Collections.emptyList();
        }
        List<View> rows = new ArrayList<>(pickerProfileList.getChildCount());
        for (int index = 0; index < pickerProfileList.getChildCount(); index++) {
            rows.add(pickerProfileList.getChildAt(index));
        }
        return Collections.unmodifiableList(rows);
    }

    String pickerBoundProfileIdForTesting(View row) {
        if (!(row instanceof PickerProfileRow)
                || !(row.getTag() instanceof PickerProfileRowHolder)) {
            return null;
        }
        return ((PickerProfileRowHolder) row.getTag()).profileId;
    }

    boolean pickerScrollToProfileForTesting(String profileId) {
        if (pickerProfileList == null || pickerProfileAdapter == null) {
            return false;
        }
        int position = pickerProfileAdapter.positionOf(profileId);
        if (position < 0) {
            return false;
        }
        recycleAttachedPickerRowsToward(position);
        pickerProfileList.setSelectionFromTop(position, 0);
        return true;
    }

    private void recycleAttachedPickerRowsToward(int position) {
        int remainingSteps = pickerProfileAdapter.getCount();
        while (remainingSteps-- > 0 && pickerProfileList.getChildCount() > 0) {
            int firstVisible = pickerProfileList.getFirstVisiblePosition();
            int lastVisible = pickerProfileList.getLastVisiblePosition();
            if (position >= firstVisible && position <= lastVisible) {
                return;
            }
            View edge = position < firstVisible
                    ? pickerProfileList.getChildAt(0)
                    : pickerProfileList.getChildAt(pickerProfileList.getChildCount() - 1);
            int distance = edge.getHeight() + pickerProfileList.getDividerHeight();
            if (distance <= 0) {
                return;
            }
            pickerProfileList.scrollListBy(position < firstVisible ? -distance : distance);
            int nextFirstVisible = pickerProfileList.getFirstVisiblePosition();
            int nextLastVisible = pickerProfileList.getLastVisiblePosition();
            if (nextFirstVisible == firstVisible && nextLastVisible == lastVisible) {
                return;
            }
        }
    }

    boolean pickerAttachedRowsHaveExactSelectionStateForTesting(String activeProfileId) {
        if (pickerProfileList == null
                || pickerProfileAdapter == null
                || pickerProfileAdapter.positionOf(activeProfileId) < 0
                || pickerProfileList.getChildCount() == 0) {
            return false;
        }
        int attachedActiveRows = 0;
        for (View view : pickerAttachedRowsForTesting()) {
            if (!(view instanceof PickerProfileRow)
                    || !(view.getTag() instanceof PickerProfileRowHolder)) {
                return false;
            }
            PickerProfileRow row = (PickerProfileRow) view;
            PickerProfileRowHolder holder = (PickerProfileRowHolder) view.getTag();
            if (holder.profile == null || !holder.profile.id().equals(holder.profileId)) {
                return false;
            }
            boolean expectedActive = activeProfileId.equals(holder.profileId);
            if (expectedActive) {
                attachedActiveRows++;
            }
            CharSequence expectedMarker = expectedActive ? "✓" : "";
            String expectedDescription = pickerProfileDescription(
                    holder.profile,
                    expectedActive
            );
            if (row.isActivated() != expectedActive
                    || row.accessibilitySelectedForTesting() != expectedActive
                    || !TextUtils.equals(holder.marker.getText(), expectedMarker)
                    || !TextUtils.equals(row.getContentDescription(), expectedDescription)) {
                return false;
            }
        }
        boolean activeAttached = attachedPickerProfileRowForTesting(activeProfileId) != null;
        return attachedActiveRows == (activeAttached ? 1 : 0);
    }

    boolean pickerHasProfileForTesting(String profileId) {
        return pickerProfileRowForTesting(profileId) != null;
    }

    boolean performPickerProfileForTesting(String profileId) {
        View row = pickerProfileRowForTesting(profileId);
        return row != null && row.performClick();
    }

    boolean pickerUsesScrollingContainerForTesting() {
        return pickerProfileList != null
                && pickerProfileAdapter != null
                && pickerProfileList.getAdapter() == pickerProfileAdapter;
    }

    boolean pickerRecyclesRowsForTesting() {
        if (pickerProfileList == null
                || pickerProfileAdapter == null
                || profile == null
                || pickerProfileAdapter.getCount() < 2) {
            return false;
        }
        int activePosition = pickerProfileAdapter.positionOf(profile.id());
        if (activePosition < 0) {
            return false;
        }
        int inactivePosition = activePosition == 0 ? 1 : 0;
        View activeRow = pickerProfileAdapter.getView(activePosition, null, pickerProfileList);
        PickerProfileRowHolder activeHolder = (PickerProfileRowHolder) activeRow.getTag();
        CharSequence activeDescription = activeRow.getContentDescription();
        String selectedState = getContext().getString(R.string.selected_state);
        boolean activeStateBound = activeRow.isActivated()
                && ((PickerProfileRow) activeRow).accessibilitySelectedForTesting()
                && "✓".contentEquals(activeHolder.marker.getText())
                && activeDescription != null
                && activeDescription.toString().contains(selectedState);

        View rebound = pickerProfileAdapter.getView(
                inactivePosition,
                activeRow,
                pickerProfileList
        );
        PickerProfileRowHolder holder = (PickerProfileRowHolder) rebound.getTag();
        KeyboardProfile expected = pickerProfileAdapter.getItem(inactivePosition);
        CharSequence reboundDescription = rebound.getContentDescription();
        return activeStateBound
                && activeRow == rebound
                && holder.profile == expected
                && holder.labels.getText().toString().contains(expected.nativeName())
                && expected.id().equals(holder.profileId)
                && !rebound.isActivated()
                && !((PickerProfileRow) rebound).accessibilitySelectedForTesting()
                && TextUtils.isEmpty(holder.marker.getText())
                && reboundDescription != null
                && !reboundDescription.toString().contains(selectedState);
    }

    boolean pickerIsAccessibilityModalForTesting() {
        return pickerAccessibilityModal
                && keyboardContent.getVisibility() == INVISIBLE
                && keyboardContent.getImportantForAccessibility()
                == IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
                && pickerSheet.getImportantForAccessibility() == IMPORTANT_FOR_ACCESSIBILITY_YES;
    }

    boolean pickerBlocksUnderlyingKeyboardForTesting() {
        return pickerSheet.getVisibility() == VISIBLE
                && pickerSheet.isClickable()
                && keyboardContent.getVisibility() == INVISIBLE;
    }

    boolean pickerAccessibilityRestoredForTesting() {
        return !pickerAccessibilityModal
                && pickerSheet.getVisibility() == GONE
                && pickerInitialFocus == null
                && pickerReturnFocus == null
                && keyboardContent.getVisibility() == keyboardContentVisibility
                && keyboardContent.getImportantForAccessibility()
                == keyboardContentAccessibilityImportance
                && pickerSheet.getImportantForAccessibility()
                == pickerSheetAccessibilityImportance;
    }

    boolean pickerProfileSelectedForTesting(String profileId) {
        View row = pickerProfileRowForTesting(profileId);
        return row instanceof PickerProfileRow
                && ((PickerProfileRow) row).accessibilitySelectedForTesting();
    }

    boolean pickerAttachedProfileSelectedForTesting(String profileId) {
        View row = attachedPickerProfileRowForTesting(profileId);
        return row instanceof PickerProfileRow
                && ((PickerProfileRow) row).accessibilitySelectedForTesting();
    }

    CharSequence pickerProfileDescriptionForTesting(String profileId) {
        View row = pickerProfileRowForTesting(profileId);
        return row == null ? null : row.getContentDescription();
    }

    SuggestionSnapshot.Status suggestionStatusForTesting() {
        return displayedSuggestionStatus;
    }

    int visibleCandidateCountForTesting() {
        int visible = 0;
        for (TextView candidate : candidateViews) {
            if (candidate.getVisibility() == VISIBLE) {
                visible++;
            }
        }
        return visible;
    }

    boolean textKeyUsesBundledNewaTypefaceForTesting(String text) {
        return keyboardSurface.textKeyUsesBundledNewaTypefaceForTesting(text);
    }

    boolean allVisibleNewaKeysUseBundledTypefaceForTesting() {
        return keyboardSurface.allVisibleNewaKeysUseBundledTypefaceForTesting();
    }

    boolean candidateUsesBundledNewaTypefaceForTesting(String text) {
        for (TextView candidate : candidateViews) {
            if (text.contentEquals(candidate.getText())) {
                return scriptTypefaces.usesBundledNewa(candidate);
            }
        }
        return false;
    }

    boolean bundledNewaTypefaceCoversForTesting(String text) {
        return scriptTypefaces.bundledNewaCovers(text);
    }

    boolean candidateAccessibilityContractForTesting() {
        if (candidateRow.getAccessibilityLiveRegion() != ACCESSIBILITY_LIVE_REGION_NONE
                || !candidateRow.suppressesAutomaticPopulationForTesting()) {
            return false;
        }
        for (TextView candidate : candidateViews) {
            CharSequence value = candidate.getText();
            if (candidate.getVisibility() == VISIBLE) {
                if (TextUtils.isEmpty(value)
                        || !candidate.isClickable()
                        || !candidate.isFocusable()
                        || !TextUtils.equals(
                                candidate.getContentDescription(),
                                getContext().getString(
                                        R.string.suggestion_description,
                                        value
                                )
                        )) {
                    return false;
                }
            } else if (!TextUtils.isEmpty(value)
                    || candidate.getContentDescription() != null) {
                return false;
            }
        }
        return true;
    }

    boolean performSuggestionRecoveryForTesting() {
        return suggestionStatusAction.getVisibility() == VISIBLE
                && suggestionStatusAction.performClick();
    }

    private View pickerProfileRowForTesting(String profileId) {
        if (pickerProfileList == null || pickerProfileAdapter == null) {
            return null;
        }
        View attached = attachedPickerProfileRowForTesting(profileId);
        if (attached != null) {
            return attached;
        }
        int position = pickerProfileAdapter.positionOf(profileId);
        return position < 0
                ? null
                : pickerProfileAdapter.getView(position, null, pickerProfileList);
    }

    private View attachedPickerProfileRowForTesting(String profileId) {
        if (pickerProfileList == null) {
            return null;
        }
        for (int index = 0; index < pickerProfileList.getChildCount(); index++) {
            View row = pickerProfileList.getChildAt(index);
            Object tag = row.getTag();
            if (tag instanceof PickerProfileRowHolder
                    && profileId.equals(((PickerProfileRowHolder) tag).profileId)) {
                return row;
            }
        }
        return null;
    }

    private void renderKeyboard() {
        if (profile == null || uiState == null) {
            return;
        }
        if (uiState.panel() == KeyboardUiState.Panel.EMOJI) {
            showEmojiPanel();
            return;
        }
        emojiPanel.setVisibility(GONE);
        updateToolbarToggleStates();
        keyboardSurface.setVisibility(VISIBLE);
        if (keyAlternates == null) {
            keyAlternates = KeyAlternatesCatalog.load(getContext());
        }
        KeyboardLayouts.Layout layout = uiState.transliterating()
                ? KeyboardLayouts.forTransliteration(profile, uiState)
                : keyAlternates.attach(KeyboardLayouts.forProfile(profile, uiState));
        keyboardSurface.render(layout);
    }

    private void showEmojiPanel() {
        if (emojiCatalog == null) {
            emojiCatalog = EmojiCatalog.load(getContext());
        }
        keyPreviewOverlay.hide();
        emojiPanel.bind(
                emojiCatalog,
                !emojiHistoryAllowed || keyboardPreferences == null
                        ? Collections.emptyList()
                        : keyboardPreferences.recentEmoji()
        );
        keyboardSurface.setVisibility(GONE);
        emojiPanel.setVisibility(VISIBLE);
        updateToolbarToggleStates();
    }

    private void updateToolbarToggleStates() {
        boolean phonetic = uiState != null && uiState.transliterating();
        boolean emoji = uiState != null && uiState.panel() == KeyboardUiState.Panel.EMOJI;
        styleToolbarToggle(
                translitChip,
                phonetic,
                phonetic ? R.string.phonetic_input_on : R.string.phonetic_input_off
        );
        styleToolbarToggle(
                emojiChip,
                emoji,
                emoji ? R.string.emoji_panel_open : R.string.emoji_panel_closed
        );
    }

    private void styleToolbarToggle(TextView view, boolean active, int descriptionResource) {
        view.setActivated(active);
        view.setSelected(active);
        view.setContentDescription(getContext().getString(descriptionResource));
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            view.setStateDescription(getContext().getString(
                    active ? R.string.state_on : R.string.state_off
            ));
        }
        int color = active && activeTheme != null
                ? activeTheme.pressedColor()
                : Color.TRANSPARENT;
        view.setBackground(rounded(color, dp(12)));
    }

    private void enterPickerAccessibility(View initialFocus, View returnFocus) {
        keyboardContentVisibility = keyboardContent.getVisibility();
        keyboardContentAccessibilityImportance = keyboardContent.getImportantForAccessibility();
        pickerSheetAccessibilityImportance = pickerSheet.getImportantForAccessibility();
        pickerReturnFocus = returnFocus == null ? profileChip : returnFocus;
        pickerReturnHadInputFocus = pickerReturnFocus.hasFocus();
        pickerInitialFocus = initialFocus;
        pickerAccessibilityModal = true;
        int generation = ++pickerAccessibilityGeneration;

        keyboardContent.setVisibility(INVISIBLE);
        keyboardContent.setImportantForAccessibility(
                IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
        );
        pickerSheet.setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            pickerSheet.setAccessibilityPaneTitle(
                    getContext().getString(R.string.choose_language)
            );
        }
        initialFocus.post(() -> {
            if (!pickerAccessibilityModal
                    || pickerAccessibilityGeneration != generation
                    || pickerInitialFocus != initialFocus
                    || pickerSheet.getVisibility() != VISIBLE) {
                return;
            }
            initialFocus.requestFocus();
        });
    }

    private void closeLanguagePicker() {
        closeLanguagePicker(true, false);
    }

    private void closeLanguagePicker(boolean restoreFocus, boolean forceProfileChipFocus) {
        if (pickerSheet.getVisibility() != VISIBLE && !pickerAccessibilityModal) {
            return;
        }
        View previousPickerFocus = pickerInitialFocus;
        if (previousPickerFocus != null) {
            previousPickerFocus.performAccessibilityAction(
                    AccessibilityNodeInfo.ACTION_CLEAR_ACCESSIBILITY_FOCUS,
                    null
            );
            previousPickerFocus.clearFocus();
        }
        pickerSheet.clearFocus();
        pickerSheet.setVisibility(GONE);

        if (!pickerAccessibilityModal) {
            return;
        }
        View returnFocus = forceProfileChipFocus ? profileChip : pickerReturnFocus;
        boolean restoreInputFocus = restoreFocus
                && (forceProfileChipFocus || pickerReturnHadInputFocus);
        keyboardContent.setVisibility(keyboardContentVisibility);
        keyboardContent.setImportantForAccessibility(keyboardContentAccessibilityImportance);
        pickerSheet.setImportantForAccessibility(pickerSheetAccessibilityImportance);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            pickerSheet.setAccessibilityPaneTitle(null);
        }
        pickerInitialFocus = null;
        pickerReturnFocus = null;
        pickerAccessibilityModal = false;
        pickerReturnHadInputFocus = false;
        int generation = ++pickerAccessibilityGeneration;
        if (!restoreFocus || returnFocus == null) {
            return;
        }
        returnFocus.post(() -> {
            if (pickerAccessibilityModal || pickerAccessibilityGeneration != generation) {
                return;
            }
            if (restoreInputFocus) {
                returnFocus.requestFocus();
            }
        });
    }

    private TextView toolbarButton(String text, String description) {
        TextView view = textView(text, 15, textColor);
        view.setGravity(Gravity.CENTER);
        view.setContentDescription(description);
        view.setClickable(true);
        view.setFocusable(true);
        view.setMinWidth(dp(48));
        view.setMinHeight(dp(48));
        view.setBackground(rounded(Color.TRANSPARENT, dp(12)));
        return view;
    }

    private void applyToolbarIcon(TextView view, int drawableId) {
        Drawable icon = getContext().getDrawable(drawableId);
        if (icon == null) {
            return;
        }
        int size = dp(22);
        icon.setBounds(0, 0, size, size);
        toolbarIconTintColor = activeTheme == null ? textColor : activeTheme.textColor();
        icon.setTint(toolbarIconTintColor);
        view.setText("");
        view.setCompoundDrawables(icon, null, null, null);
    }

    private void tintToolbarIcon(TextView view, int color) {
        Drawable icon = view.getCompoundDrawables()[0];
        if (icon == null) {
            return;
        }
        toolbarIconTintColor = color;
        icon.mutate().setTint(color);
        view.invalidate();
    }

    boolean chromeThemeMatchesForTesting(KeyboardTheme theme) {
        return profileChip.getCurrentTextColor() == theme.textColor()
                && settingsChip.getCurrentTextColor() == theme.textColor()
                && emojiChip.getCurrentTextColor() == theme.textColor()
                && translitChip.getCurrentTextColor() == theme.textColor()
                && toolbarIconTintMatches(profileChip, theme.textColor())
                && toolbarIconTintMatches(settingsChip, theme.textColor())
                && emojiPanel.themeMatchesForTesting(theme);
    }

    boolean transliterationToggleStateForTesting(boolean expected) {
        return toolbarToggleStateMatches(
                translitChip,
                expected,
                expected ? R.string.phonetic_input_on : R.string.phonetic_input_off
        );
    }

    boolean transliterationToggleUsesNeutralSymbolForTesting() {
        return getContext().getString(R.string.phonetic_input_symbol).contentEquals(
                translitChip.getText()
        );
    }

    boolean emojiToggleStateForTesting(boolean expected) {
        return toolbarToggleStateMatches(
                emojiChip,
                expected,
                expected ? R.string.emoji_panel_open : R.string.emoji_panel_closed
        );
    }

    private boolean toolbarToggleStateMatches(
            TextView view,
            boolean expected,
            int descriptionResource
    ) {
        return view.isActivated() == expected
                && view.isSelected() == expected
                && getContext().getString(descriptionResource).contentEquals(
                view.getContentDescription()
        );
    }

    boolean pickerThemeMatchesForTesting(KeyboardTheme theme) {
        if (pickerSheet.getVisibility() != VISIBLE
                || !(pickerSheet.getBackground() instanceof ColorDrawable)
                || ((ColorDrawable) pickerSheet.getBackground()).getColor()
                != theme.surfaceColor()
                || pickerSheet.getChildCount() < 3) {
            return false;
        }
        View headerView = pickerSheet.getChildAt(0);
        View actionsView = pickerSheet.getChildAt(pickerSheet.getChildCount() - 1);
        if (!(headerView instanceof LinearLayout) || !(actionsView instanceof LinearLayout)) {
            return false;
        }
        LinearLayout header = (LinearLayout) headerView;
        LinearLayout actions = (LinearLayout) actionsView;
        return header.getChildCount() == 2
                && actions.getChildCount() == 2
                && textColorMatches(header.getChildAt(0), theme.textColor())
                && textColorMatches(header.getChildAt(1), theme.textColor())
                && textColorMatches(actions.getChildAt(0), theme.textColor())
                && textColorMatches(actions.getChildAt(1), theme.textColor());
    }

    private boolean textColorMatches(View view, int color) {
        return view instanceof TextView && ((TextView) view).getCurrentTextColor() == color;
    }

    private boolean toolbarIconTintMatches(TextView view, int color) {
        Drawable icon = view.getCompoundDrawables()[0];
        return icon != null && toolbarIconTintColor == color;
    }

    private TextView pickerButton(String text, String description) {
        TextView view = textView(text, 17, currentThemeTextColor());
        view.setGravity(Gravity.CENTER_VERTICAL);
        view.setPadding(dp(12), dp(8), dp(12), dp(8));
        view.setContentDescription(description);
        view.setClickable(true);
        view.setFocusable(true);
        view.setMinHeight(dp(52));
        view.setMaxLines(2);
        view.setEllipsize(TextUtils.TruncateAt.END);
        view.setBackground(pickerBackground());
        return view;
    }

    private View createPickerProfileRow() {
        PickerProfileRow row = new PickerProfileRow();
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(dp(8), 0, dp(12), 0);
        row.setClickable(true);
        row.setFocusable(true);
        row.setMinimumHeight(dp(52));

        TextView marker = textView("", 20, currentThemeTextColor());
        marker.setGravity(Gravity.CENTER);
        marker.setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
        row.addView(marker, new LinearLayout.LayoutParams(dp(44), LayoutParams.MATCH_PARENT));

        TextView labels = textView("", 17, currentThemeTextColor());
        labels.setPadding(0, dp(8), 0, dp(8));
        labels.setMaxLines(2);
        labels.setEllipsize(TextUtils.TruncateAt.END);
        labels.setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
        row.addView(labels, new LinearLayout.LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f));
        row.setTag(new PickerProfileRowHolder(marker, labels));
        return row;
    }

    private void bindPickerProfileRow(View view, KeyboardProfile candidate) {
        PickerProfileRowHolder holder = (PickerProfileRowHolder) view.getTag();
        boolean active = profile != null && candidate.id().equals(profile.id());
        String subtitle = candidate.nativeName().equals(candidate.displayName())
                ? candidate.detail()
                : candidate.displayName() + " · " + candidate.detail();
        holder.profile = candidate;
        holder.profileId = candidate.id();
        holder.marker.setText(active ? "✓" : "");
        String labels = candidate.nativeName() + "\n" + subtitle;
        holder.labels.setText(labels);
        scriptTypefaces.apply(holder.labels, labels, holder.labelsDefaultTypeface);
        view.setContentDescription(pickerProfileDescription(candidate, active));
        ((PickerProfileRow) view).setProfileSelected(active);
        view.setBackground(pickerBackground());
        view.setOnClickListener(row -> {
            PickerProfileRowHolder clicked = (PickerProfileRowHolder) row.getTag();
            String selectedProfileId = clicked.profileId;
            closeLanguagePicker(true, true);
            listener.onProfileSelected(selectedProfileId);
        });
    }

    private String pickerProfileDescription(KeyboardProfile candidate, boolean active) {
        String description = candidate.nativeName().equals(candidate.displayName())
                ? candidate.displayName() + ", " + candidate.detail()
                : candidate.nativeName() + ", " + candidate.displayName() + ", "
                + candidate.detail();
        if (!active) {
            return description;
        }
        return getContext().getString(
                R.string.language_profile_selected_description,
                description,
                getContext().getString(R.string.selected_state)
        );
    }

    private GradientDrawable pickerBackground() {
        int color = activeTheme == null
                ? ((getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES
                ? Color.rgb(45, 43, 50)
                : Color.rgb(235, 232, 241))
                : activeTheme.actionKeyColor();
        return rounded(color, dp(12));
    }

    private int currentThemeTextColor() {
        return activeTheme == null ? textColor : activeTheme.textColor();
    }

    private LinearLayout.LayoutParams pickerActionParams(int width, float weight) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                width,
                LayoutParams.WRAP_CONTENT,
                weight
        );
        params.setMargins(dp(3), dp(3), dp(3), dp(3));
        return params;
    }

    private TextView textView(String text, int sizeSp, int color) {
        TextView view = new TextView(getContext());
        view.setText(text);
        view.setTextColor(color);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp);
        return view;
    }

    private GradientDrawable rounded(int color, int radius) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(radius);
        return drawable;
    }

    private int dp(int value) {
        return Math.round(TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP,
                value,
                getResources().getDisplayMetrics()
        ));
    }

    private final class PickerProfileAdapter extends BaseAdapter {
        private final List<KeyboardProfile> profiles;

        PickerProfileAdapter(List<KeyboardProfile> profiles) {
            this.profiles = Collections.unmodifiableList(new ArrayList<>(profiles));
        }

        @Override
        public int getCount() {
            return profiles.size();
        }

        @Override
        public KeyboardProfile getItem(int position) {
            return profiles.get(position);
        }

        @Override
        public long getItemId(int position) {
            return position;
        }

        @Override
        public View getView(int position, View convertView, ViewGroup parent) {
            View row = convertView;
            if (!(row instanceof PickerProfileRow)
                    || !(row.getTag() instanceof PickerProfileRowHolder)) {
                row = createPickerProfileRow();
            }
            bindPickerProfileRow(row, getItem(position));
            return row;
        }

        int positionOf(String profileId) {
            for (int position = 0; position < profiles.size(); position++) {
                if (profileId.equals(profiles.get(position).id())) {
                    return position;
                }
            }
            return -1;
        }
    }

    private static final class PickerProfileRowHolder {
        final TextView marker;
        final TextView labels;
        final Typeface labelsDefaultTypeface;
        KeyboardProfile profile;
        String profileId;

        PickerProfileRowHolder(TextView marker, TextView labels) {
            this.marker = marker;
            this.labels = labels;
            this.labelsDefaultTypeface = labels.getTypeface();
        }
    }

    /**
     * Candidate changes on every key must not become a parent announcement. Each
     * visible child remains an independently labelled, focusable action.
     */
    private final class SuggestionCandidateRow extends LinearLayout {
        SuggestionCandidateRow() {
            super(NepaInputView.this.getContext());
        }

        @Override
        public boolean dispatchPopulateAccessibilityEvent(AccessibilityEvent event) {
            return true;
        }

        boolean suppressesAutomaticPopulationForTesting() {
            AccessibilityEvent event = AccessibilityEvent.obtain(
                    AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
            );
            try {
                return dispatchPopulateAccessibilityEvent(event) && event.getText().isEmpty();
            } finally {
                event.recycle();
            }
        }
    }

    /** ListView owns View.selected; this keeps product-current semantics holder-backed. */
    private final class PickerProfileRow extends LinearLayout {
        private boolean profileSelected;

        PickerProfileRow() {
            super(NepaInputView.this.getContext());
        }

        void setProfileSelected(boolean selected) {
            profileSelected = selected;
            setActivated(selected);
        }

        @Override
        public void onInitializeAccessibilityNodeInfo(AccessibilityNodeInfo info) {
            super.onInitializeAccessibilityNodeInfo(info);
            info.setSelected(profileSelected);
        }

        boolean accessibilitySelectedForTesting() {
            AccessibilityNodeInfo info = AccessibilityNodeInfo.obtain();
            try {
                onInitializeAccessibilityNodeInfo(info);
                return info.isSelected();
            } finally {
                info.recycle();
            }
        }
    }
}
