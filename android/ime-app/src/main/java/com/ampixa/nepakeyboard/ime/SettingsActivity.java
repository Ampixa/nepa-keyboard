package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.database.ContentObserver;
import android.graphics.Color;
import android.graphics.Rect;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.InputMethodInfo;
import android.view.inputmethod.InputMethodManager;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.CompoundButton;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Setup plus virtualized, searchable management for every generated profile. */
public final class SettingsActivity extends Activity {
    private static final String STATE_LANGUAGE_QUERY = "language_query";
    private static final String STATE_LIST_POSITION = "language_list_position";
    private static final String STATE_LIST_OFFSET = "language_list_offset";
    private static final String STATE_TYPING_OBSERVED = "setup_typing_observed";
    private static final int NO_LIST_POSITION = -1;
    private static final long EMPTY_ROW_ID = Long.MIN_VALUE;
    private static final int VIEW_TYPE_EMPTY = 0;
    private static final int VIEW_TYPE_LANGUAGE = 1;

    enum LanguageSection {
        ENABLED,
        AVAILABLE_TO_ENABLE,
        LATER
    }

    private LanguagePreferences languagePreferences;
    private KeyboardPreferences keyboardPreferences;
    private LanguageAdapter languageAdapter;
    private ListView languageList;
    private String languageQuery = "";
    private int savedListPosition = NO_LIST_POSITION;
    private int savedListOffset;
    private boolean typingObserved;
    private boolean setupObserversRegistered;
    private ContentObserver imeSettingsObserver;
    private SharedPreferences.OnSharedPreferenceChangeListener languageStateListener;
    private TextView setupProgress;
    private TextView setupEnableStep;
    private TextView setupSelectStep;
    private TextView setupLanguagesStep;
    private TextView setupTypingStep;
    private TextView setupCompletion;
    private Button setupSelectButton;
    private EditText setupTypingEditor;
    private EditText languageSearch;
    private ActivitySystemBarInsets.State systemBarInsets;
    private int surfaceColor;
    private int cardColor;
    private int textColor;
    private int secondaryTextColor;
    private int accentColor;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        languagePreferences = new LanguagePreferences(this);
        keyboardPreferences = new KeyboardPreferences(this);
        verifyStableProfileIds();
        boolean dark = (getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        surfaceColor = dark ? Color.rgb(23, 22, 27) : Color.rgb(246, 245, 250);
        cardColor = dark ? Color.rgb(45, 43, 50) : Color.WHITE;
        textColor = dark ? Color.rgb(246, 243, 248) : Color.rgb(31, 29, 35);
        secondaryTextColor = dark ? Color.rgb(199, 194, 204) : Color.rgb(92, 88, 99);
        accentColor = dark ? Color.rgb(197, 192, 255) : Color.rgb(79, 70, 165);
        imeSettingsObserver = new ContentObserver(new Handler(Looper.getMainLooper())) {
            @Override
            public void onChange(boolean selfChange) {
                refreshSetupStateViews();
            }
        };
        languageStateListener = (preferences, key) -> runOnUiThread(() -> {
            if (!setupObserversRegistered) {
                return;
            }
            if (languageAdapter != null
                    && !languageAdapter.enabledProfileSnapshotMatchesCurrent()) {
                render();
            } else {
                refreshSetupStateViews();
            }
        });
        if (savedInstanceState != null) {
            languageQuery = savedInstanceState.getString(STATE_LANGUAGE_QUERY, "");
            savedListPosition = savedInstanceState.getInt(
                    STATE_LIST_POSITION,
                    NO_LIST_POSITION
            );
            savedListOffset = savedInstanceState.getInt(STATE_LIST_OFFSET, 0);
            typingObserved = savedInstanceState.getBoolean(STATE_TYPING_OBSERVED, false);
        }
    }

    @Override
    protected void onStart() {
        super.onStart();
        if (!setupObserversRegistered) {
            getContentResolver().registerContentObserver(
                    Settings.Secure.getUriFor(Settings.Secure.ENABLED_INPUT_METHODS),
                    false,
                    imeSettingsObserver
            );
            getContentResolver().registerContentObserver(
                    Settings.Secure.getUriFor(Settings.Secure.DEFAULT_INPUT_METHOD),
                    false,
                    imeSettingsObserver
            );
            languagePreferences.registerStateListener(languageStateListener);
            setupObserversRegistered = true;
        }
        refreshSetupStateViews();
    }

    @Override
    protected void onResume() {
        super.onResume();
        render();
    }

    @Override
    protected void onStop() {
        if (setupObserversRegistered) {
            languagePreferences.unregisterStateListener(languageStateListener);
            getContentResolver().unregisterContentObserver(imeSettingsObserver);
            setupObserversRegistered = false;
        }
        super.onStop();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        captureListPosition();
        outState.putString(STATE_LANGUAGE_QUERY, languageQuery);
        outState.putInt(STATE_LIST_POSITION, savedListPosition);
        outState.putInt(STATE_LIST_OFFSET, savedListOffset);
        outState.putBoolean(STATE_TYPING_OBSERVED, currentSetupState().typingTested());
        super.onSaveInstanceState(outState);
    }

    private void render() {
        captureListPosition();
        LanguageAdapter nextAdapter = new LanguageAdapter();
        ListView nextList = new ListView(this);
        nextList.setBackgroundColor(surfaceColor);
        nextList.setDivider(null);
        nextList.setDividerHeight(0);
        nextList.setItemsCanFocus(true);
        // Insets are expressed as root padding. Keep scrolled content out of that
        // protected area so large text never draws underneath status-bar icons.
        nextList.setClipToPadding(true);
        nextList.setPadding(0, 0, 0, dp(16));
        nextList.addHeaderView(header(nextAdapter), null, false);
        nextList.addFooterView(privacyFooter(), null, false);
        nextList.setAdapter(nextAdapter);
        languageAdapter = nextAdapter;
        languageList = nextList;
        setContentView(nextList);
        systemBarInsets = ActivitySystemBarInsets.install(
                this,
                nextList,
                true,
                this::keepTypingEditorVisible
        );
        if (savedListPosition != NO_LIST_POSITION) {
            nextList.setSelectionFromTop(savedListPosition, savedListOffset);
        }
    }

    private void captureListPosition() {
        if (languageList == null || languageList.getChildCount() == 0) {
            return;
        }
        savedListPosition = languageList.getFirstVisiblePosition();
        savedListOffset = languageList.getChildAt(0).getTop();
    }

    private View header(LanguageAdapter adapter) {
        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.VERTICAL);
        header.setPadding(dp(20), dp(24), dp(20), 0);
        addText(header, getString(R.string.setup_title), 28, textColor, 4);
        addText(header, getString(R.string.setup_summary), 16, secondaryTextColor, 20);

        LinearLayout setupCard = card();
        setupProgress = text("", 18, textColor);
        setupProgress.setPadding(dp(4), dp(4), dp(4), dp(12));
        setupProgress.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        setupCard.addView(setupProgress);

        TextView privacyReassurance = text(
                getString(R.string.setup_privacy_reassurance),
                14,
                secondaryTextColor
        );
        privacyReassurance.setPadding(dp(4), 0, dp(4), dp(12));
        setupCard.addView(privacyReassurance);

        setupEnableStep = setupStepView();
        setupCard.addView(setupEnableStep);
        Button enable = actionButton(getString(R.string.enable_keyboard));
        enable.setOnClickListener(view -> startActivity(
                new Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)
        ));
        setupCard.addView(enable);

        setupSelectStep = setupStepView();
        setupCard.addView(setupSelectStep);
        setupSelectButton = actionButton(getString(R.string.choose_keyboard));
        setupSelectButton.setOnClickListener(
                view -> inputMethodManager().showInputMethodPicker()
        );
        setupCard.addView(setupSelectButton);

        setupLanguagesStep = setupStepView();
        setupCard.addView(setupLanguagesStep);
        Button manageLanguages = actionButton(getString(R.string.review_enabled_languages));
        manageLanguages.setOnClickListener(view -> focusLanguageManager());
        setupCard.addView(manageLanguages);

        setupTypingStep = setupStepView();
        setupCard.addView(setupTypingStep);
        setupTypingEditor = new EditText(this);
        setupTypingEditor.setInputType(
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        );
        setupTypingEditor.setHint(R.string.test_typing_hint);
        setupTypingEditor.setContentDescription(getString(R.string.test_typing_description));
        setupTypingEditor.setMinHeight(dp(56));
        setupTypingEditor.setSaveEnabled(false);
        setupTypingEditor.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
        setupTypingEditor.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence value, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence value, int start, int before, int count) {
            }

            @Override
            public void afterTextChanged(Editable value) {
                recordTypingObservation(value);
            }
        });
        EditText typingEditorForLayout = setupTypingEditor;
        typingEditorForLayout.setOnFocusChangeListener((view, hasFocus) -> {
            if (hasFocus) {
                view.post(this::keepTypingEditorVisible);
            }
        });
        setupCard.addView(
                setupTypingEditor,
                fullWidth(ViewGroup.LayoutParams.WRAP_CONTENT, 8)
        );

        setupCompletion = text(getString(R.string.setup_complete_summary), 15, accentColor);
        setupCompletion.setPadding(dp(4), dp(4), dp(4), dp(4));
        setupCard.addView(setupCompletion);
        header.addView(setupCard, sectionParams());
        refreshSetupStateViews();

        // Kept above the language list so it never sits behind 74 scrollable rows.
        header.addView(keyboardSettingsCard(), sectionParams());

        addText(header, getString(R.string.languages), 22, textColor, 8);
        Button current = actionButton(
                getString(R.string.choose_current_language)
                        + ": "
                        + languagePreferences.activeProfile().nativeName()
        );
        current.setOnClickListener(view -> showCurrentProfilePicker());
        header.addView(current, fullWidth(dp(52), 8));

        EditText search = new EditText(this);
        languageSearch = search;
        search.setSingleLine(true);
        search.setHint(R.string.search_languages);
        search.setContentDescription(getString(R.string.search_languages));
        search.setText(languageQuery);
        search.setSelection(search.length());
        search.setMinHeight(dp(48));
        search.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence value, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence value, int start, int before, int count) {
            }

            @Override
            public void afterTextChanged(Editable value) {
                languageQuery = value.toString();
                savedListPosition = 0;
                savedListOffset = 0;
                adapter.filter(languageQuery);
                if (languageList != null) {
                    languageList.setSelection(0);
                }
            }
        });
        header.addView(search, fullWidth(ViewGroup.LayoutParams.WRAP_CONTENT, 8));
        return header;
    }

    private View privacyFooter() {
        LinearLayout container = new LinearLayout(this);
        container.setOrientation(LinearLayout.VERTICAL);
        container.setPadding(dp(20), dp(8), dp(20), dp(16));
        LinearLayout privacy = card();
        TextView privacyTitle = text(getString(R.string.privacy_title), 18, textColor);
        privacyTitle.setPadding(dp(4), dp(4), dp(4), dp(6));
        privacy.addView(privacyTitle);
        TextView privacySummary = text(getString(R.string.privacy_summary), 15, secondaryTextColor);
        privacySummary.setPadding(dp(4), 0, dp(4), dp(4));
        privacy.addView(privacySummary);
        container.addView(privacy, sectionParams());

        LinearLayout notices = card();
        TextView noticesTitle = text(getString(R.string.dictionary_notices_title), 18, textColor);
        noticesTitle.setPadding(dp(4), dp(4), dp(4), dp(6));
        notices.addView(noticesTitle);
        TextView noticesSummary = text(
                getString(R.string.dictionary_notices_short_summary),
                15,
                secondaryTextColor
        );
        noticesSummary.setPadding(dp(4), 0, dp(4), dp(4));
        notices.addView(noticesSummary);
        Button openNotices = actionButton(getString(R.string.view_dictionary_notices));
        openNotices.setContentDescription(getString(R.string.view_dictionary_notices));
        openNotices.setOnClickListener(view -> startActivity(
                new Intent(this, NoticesActivity.class)
        ));
        notices.addView(openNotices);
        container.addView(notices, sectionParams());
        return container;
    }

    /** Reviewed shell preferences. Every control writes through immediately. */
    private LinearLayout keyboardSettingsCard() {
        LinearLayout keyboardCard = card();
        TextView heading = text(getString(R.string.keyboard_settings_title), 18, textColor);
        heading.setPadding(dp(4), dp(4), dp(4), dp(6));
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            heading.setAccessibilityHeading(true);
        }
        keyboardCard.addView(heading);

        keyboardCard.addView(preferenceSwitch(
                getString(R.string.key_preview_title),
                getString(R.string.key_preview_summary),
                keyboardPreferences.keyPreviewEnabled(),
                keyboardPreferences::setKeyPreviewEnabled
        ));
        keyboardCard.addView(preferenceSwitch(
                getString(R.string.keypress_sound_title),
                getString(R.string.keypress_sound_summary),
                keyboardPreferences.soundEnabled(),
                keyboardPreferences::setSoundEnabled
        ));
        keyboardCard.addView(preferenceSwitch(
                getString(R.string.keypress_vibration_title),
                getString(R.string.keypress_vibration_summary),
                keyboardPreferences.hapticsEnabled(),
                keyboardPreferences::setHapticsEnabled
        ));
        keyboardCard.addView(preferenceSwitch(
                getString(R.string.suggestions_title),
                getString(R.string.suggestions_summary),
                keyboardPreferences.suggestionsEnabled(),
                keyboardPreferences::setSuggestionsEnabled
        ));
        keyboardCard.addView(keyboardHeightRow());
        keyboardCard.addView(themeRow());
        return keyboardCard;
    }

    /** Shows every bundled theme with the current selection, then writes through. */
    private View themeRow() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(dp(4), dp(6), dp(4), dp(6));

        TextView title = text(getString(R.string.theme_title), 16, textColor);
        title.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        row.addView(title, new LinearLayout.LayoutParams(
                0,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                1f
        ));

        Button chooser = actionButton("");
        Runnable refresh = () -> {
            KeyboardTheme active = KeyboardTheme.resolve(this, keyboardPreferences.themeId());
            String name = getString(active.displayNameResource());
            chooser.setText(name);
            chooser.setContentDescription(getString(R.string.theme_description, name));
        };
        chooser.setOnClickListener(view -> showThemePicker(refresh));
        refresh.run();
        row.addView(chooser, new LinearLayout.LayoutParams(dp(160), dp(48)));
        return row;
    }

    private void showThemePicker(Runnable onChanged) {
        List<String> ids = KeyboardTheme.bundledIds();
        String[] labels = new String[ids.size()];
        int checked = 0;
        for (int index = 0; index < ids.size(); index++) {
            KeyboardTheme theme = KeyboardTheme.resolve(this, ids.get(index));
            labels[index] = getString(theme.displayNameResource());
            if (ids.get(index).equals(keyboardPreferences.themeId())) {
                checked = index;
            }
        }
        new AlertDialog.Builder(this)
                .setTitle(R.string.theme_title)
                .setSingleChoiceItems(labels, checked, (dialog, which) -> {
                    keyboardPreferences.setThemeId(ids.get(which));
                    dialog.dismiss();
                    onChanged.run();
                })
                .setNegativeButton(R.string.close, null)
                .show();
    }

    private View preferenceSwitch(
            String title,
            String summary,
            boolean initialValue,
            java.util.function.Consumer<Boolean> onChanged
    ) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(dp(4), dp(6), dp(4), dp(6));

        LinearLayout labels = new LinearLayout(this);
        labels.setOrientation(LinearLayout.VERTICAL);
        labels.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        labels.addView(text(title, 16, textColor));
        labels.addView(text(summary, 13, secondaryTextColor));
        row.addView(labels, new LinearLayout.LayoutParams(
                0,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                1f
        ));

        Switch toggle = new Switch(this);
        toggle.setChecked(initialValue);
        // The switch owns the accessible name so the row reads once, with its state.
        toggle.setContentDescription(title);
        toggle.setMinHeight(dp(48));
        toggle.setOnCheckedChangeListener((button, checked) -> onChanged.accept(checked));
        row.addView(toggle, new LinearLayout.LayoutParams(dp(64), dp(48)));
        return row;
    }

    private View keyboardHeightRow() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(dp(4), dp(6), dp(4), dp(6));

        TextView title = text(getString(R.string.keyboard_height_title), 16, textColor);
        title.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        row.addView(title, new LinearLayout.LayoutParams(
                0,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                1f
        ));

        TextView value = text("", 16, secondaryTextColor);
        value.setGravity(Gravity.CENTER);
        value.setMinWidth(dp(64));

        Button decrease = actionButton("−");
        decrease.setContentDescription(getString(R.string.keyboard_height_decrease));
        Button increase = actionButton("+");
        increase.setContentDescription(getString(R.string.keyboard_height_increase));

        Runnable refresh = () -> {
            int percent = keyboardPreferences.heightPercent();
            value.setText(getString(R.string.keyboard_height_value, percent));
            value.setContentDescription(
                    getString(R.string.keyboard_height_description, percent)
            );
            decrease.setEnabled(percent > KeyboardMetrics.MIN_HEIGHT_PERCENT);
            increase.setEnabled(percent < KeyboardMetrics.MAX_HEIGHT_PERCENT);
        };
        decrease.setOnClickListener(view -> {
            keyboardPreferences.setHeightPercent(
                    keyboardPreferences.heightPercent() - KeyboardMetrics.HEIGHT_STEP_PERCENT
            );
            refresh.run();
        });
        increase.setOnClickListener(view -> {
            keyboardPreferences.setHeightPercent(
                    keyboardPreferences.heightPercent() + KeyboardMetrics.HEIGHT_STEP_PERCENT
            );
            refresh.run();
        });
        refresh.run();

        row.addView(decrease, new LinearLayout.LayoutParams(dp(56), dp(48)));
        row.addView(value, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                dp(48)
        ));
        row.addView(increase, new LinearLayout.LayoutParams(dp(56), dp(48)));
        return row;
    }

    private View createLanguageRow() {
        LinearLayout container = new LinearLayout(this);
        container.setOrientation(LinearLayout.VERTICAL);
        container.setPadding(dp(20), 0, dp(20), 0);
        TextView sectionHeading = text("", 20, accentColor);
        sectionHeading.setPadding(dp(4), dp(20), dp(4), 0);
        TextView languageHeading = text("", 15, secondaryTextColor);
        languageHeading.setPadding(dp(4), dp(8), dp(4), 0);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            sectionHeading.setAccessibilityHeading(true);
            languageHeading.setAccessibilityHeading(true);
        }
        container.addView(
                sectionHeading,
                fullWidth(ViewGroup.LayoutParams.WRAP_CONTENT, 0)
        );
        container.addView(
                languageHeading,
                fullWidth(ViewGroup.LayoutParams.WRAP_CONTENT, 0)
        );
        LinearLayout languageCard = card();
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);

        LinearLayout labels = new LinearLayout(this);
        labels.setOrientation(LinearLayout.VERTICAL);
        TextView name = text("", 18, textColor);
        TextView detail = text("", 14, secondaryTextColor);
        labels.addView(name);
        labels.addView(detail);
        row.addView(labels, new LinearLayout.LayoutParams(
                0,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                1f
        ));

        Switch enabled = new Switch(this);
        enabled.setMinWidth(dp(48));
        enabled.setMinHeight(dp(48));
        row.addView(enabled, new LinearLayout.LayoutParams(dp(64), dp(52)));
        languageCard.addView(row);

        TextView gate = text("", 13, secondaryTextColor);
        gate.setPadding(0, dp(8), 0, 0);
        gate.setVisibility(View.GONE);
        languageCard.addView(gate);
        container.addView(languageCard, sectionParams());
        container.setTag(new LanguageRowHolder(
                sectionHeading,
                languageHeading,
                name,
                detail,
                enabled,
                gate
        ));
        return container;
    }

    private void bindLanguageRow(
            View row,
            KeyboardProfile profile,
            LanguageSection section,
            boolean showSectionHeading,
            boolean showLanguageHeading
    ) {
        LanguageRowHolder holder = (LanguageRowHolder) row.getTag();
        if (holder.sectionHeading != null && holder.languageHeading != null) {
            holder.sectionHeading.setText(languageSectionTitle(section));
            holder.sectionHeading.setVisibility(showSectionHeading ? View.VISIBLE : View.GONE);
            holder.languageHeading.setText(profile.group() == null
                    ? profile.displayName()
                    : profile.group() + " · " + profile.displayName());
            holder.languageHeading.setVisibility(showLanguageHeading ? View.VISIBLE : View.GONE);
        }
        holder.name.setText(profile.nativeName().equals(profile.displayName())
                ? profile.nativeName()
                : profile.nativeName() + " · " + profile.displayName());
        holder.detail.setText(profile.detail());
        holder.enabled.setOnCheckedChangeListener(null);
        holder.enabled.setContentDescription(
                getString(
                        R.string.enable_language_profile_description,
                        profile.displayName(),
                        profile.detail()
                )
        );
        holder.enabled.setEnabled(section != LanguageSection.LATER);
        holder.enabled.setChecked(section == LanguageSection.ENABLED);
        attachEnabledListener(profile, holder.enabled);
        if (section != LanguageSection.LATER) {
            holder.gate.setText("");
            holder.gate.setVisibility(View.GONE);
        } else {
            holder.gate.setText(getString(
                    R.string.language_not_available_yet,
                    profile.blockedDetail()
            ));
            holder.gate.setVisibility(View.VISIBLE);
        }
    }

    private String languageSectionTitle(LanguageSection section) {
        switch (section) {
            case ENABLED:
                return getString(R.string.language_section_enabled);
            case AVAILABLE_TO_ENABLE:
                return getString(R.string.language_section_available);
            case LATER:
                return getString(R.string.language_section_later);
            default:
                throw new IllegalStateException("unknown language section: " + section);
        }
    }

    private void updateEnabled(
            KeyboardProfile profile,
            CompoundButton button,
            boolean checked
    ) {
        if (languagePreferences.setEnabled(profile.id(), checked)) {
            synchronizeAndroidSubtypes();
            if (languageAdapter == null
                    || !languageAdapter.enabledProfileSnapshotMatchesCurrent()) {
                render();
            }
            return;
        }
        button.setOnCheckedChangeListener(null);
        button.setChecked(languagePreferences.isEnabled(profile.id()));
        attachEnabledListener(profile, button);
        Toast.makeText(this, R.string.keep_one_keyboard_enabled, Toast.LENGTH_SHORT).show();
    }

    private void attachEnabledListener(KeyboardProfile profile, CompoundButton button) {
        button.setOnCheckedChangeListener((changedButton, checked) ->
                updateEnabled(profile, changedButton, checked));
    }

    private void showCurrentProfilePicker() {
        List<KeyboardProfile> enabled = languagePreferences.enabledProfiles();
        String[] labels = new String[enabled.size()];
        int checked = 0;
        for (int index = 0; index < enabled.size(); index++) {
            KeyboardProfile profile = enabled.get(index);
            labels[index] = profile.nativeName() + "  ·  " + profile.detail();
            if (profile.id().equals(languagePreferences.activeProfile().id())) {
                checked = index;
            }
        }
        new AlertDialog.Builder(this)
                .setTitle(R.string.choose_language)
                .setSingleChoiceItems(labels, checked, (dialog, which) -> {
                    languagePreferences.requestActive(enabled.get(which).id());
                    synchronizeAndroidSubtypes();
                    dialog.dismiss();
                    render();
                })
                .setNegativeButton(R.string.close, null)
                .show();
    }

    private void synchronizeAndroidSubtypes() {
        try {
            AndroidSubtypeRegistry.load(this).synchronizeEnabledProfiles(
                    languagePreferences.enabledProfiles()
            );
        } catch (RuntimeException ignoredPlatformSynchronizationFailure) {
            // The manager state is still authoritative on API 26-33 and will be
            // reconciled by the IME service when Android metadata becomes available.
        }
    }

    private TextView setupStepView() {
        TextView view = text("", 16, textColor);
        view.setPadding(dp(4), dp(8), dp(4), dp(2));
        return view;
    }

    private void focusLanguageManager() {
        if (languageSearch == null) {
            return;
        }
        languageSearch.requestFocus();
        languageSearch.announceForAccessibility(getString(R.string.languages));
    }

    private void recordTypingObservation(Editable value) {
        if (value.length() == 0 || typingObserved) {
            return;
        }
        SetupState state = currentSetupState();
        if (!state.canTestTyping()) {
            return;
        }
        typingObserved = true;
        refreshSetupStateViews();
    }

    /** Keeps the typing test inside the system-bar and IME-safe ListView viewport. */
    private void keepTypingEditorVisible() {
        if (setupTypingEditor == null
                || languageList == null
                || !setupTypingEditor.hasFocus()
                || languageList.getHeight() <= 0) {
            return;
        }
        Rect editor = new Rect();
        setupTypingEditor.getDrawingRect(editor);
        languageList.offsetDescendantRectToMyCoords(setupTypingEditor, editor);
        int margin = dp(12);
        int viewportTop = languageList.getPaddingTop() + margin;
        int viewportBottom = languageList.getHeight()
                - languageList.getPaddingBottom()
                - margin;
        if (viewportBottom > viewportTop) {
            if (editor.bottom > viewportBottom) {
                languageList.scrollListBy(editor.bottom - viewportBottom);
            } else if (editor.top < viewportTop) {
                languageList.scrollListBy(editor.top - viewportTop);
            }
        }
    }

    private void refreshSetupStateViews() {
        SetupState state = currentSetupState();
        if (setupProgress == null
                || setupEnableStep == null
                || setupSelectStep == null
                || setupLanguagesStep == null
                || setupTypingStep == null
                || setupCompletion == null
                || setupSelectButton == null
                || setupTypingEditor == null) {
            return;
        }
        setupProgress.setText(state.complete()
                ? getString(R.string.setup_complete_title)
                : getString(
                        R.string.setup_next_step,
                        setupStepTitle(state.currentStep())
                ));
        setupEnableStep.setText(setupStepLine(
                1,
                getString(R.string.setup_enable_title),
                state.imeEnabled(),
                state.currentStep() == SetupStep.ENABLE_KEYBOARD
        ));
        setupSelectStep.setText(setupStepLine(
                2,
                getString(R.string.setup_select_title),
                state.imeSelected(),
                state.currentStep() == SetupStep.SELECT_KEYBOARD
        ));
        String languageCount = getResources().getQuantityString(
                R.plurals.enabled_language_count,
                state.enabledLanguageCount(),
                state.enabledLanguageCount()
        );
        setupLanguagesStep.setText(setupStepLine(
                3,
                getString(R.string.setup_languages_title) + ": " + languageCount,
                state.languagesReady(),
                state.currentStep() == SetupStep.CHOOSE_LANGUAGES
        ));
        setupTypingStep.setText(setupStepLine(
                4,
                getString(R.string.setup_test_title),
                state.typingTested(),
                state.currentStep() == SetupStep.TEST_TYPING
        ));
        setupSelectButton.setEnabled(state.imeEnabled());
        setupTypingEditor.setEnabled(state.canTestTyping());
        setupCompletion.setVisibility(state.complete() ? View.VISIBLE : View.GONE);
    }

    private String setupStepLine(
            int number,
            String title,
            boolean complete,
            boolean current
    ) {
        int status = complete
                ? R.string.setup_step_complete
                : current ? R.string.setup_step_next : R.string.setup_step_waiting;
        return getString(R.string.setup_step_status, number, title, getString(status));
    }

    private String setupStepTitle(SetupStep step) {
        switch (step) {
            case ENABLE_KEYBOARD:
                return getString(R.string.setup_enable_title);
            case SELECT_KEYBOARD:
                return getString(R.string.setup_select_title);
            case CHOOSE_LANGUAGES:
                return getString(R.string.setup_languages_title);
            case TEST_TYPING:
                return getString(R.string.setup_test_title);
            case COMPLETE:
                return getString(R.string.setup_complete_title);
            default:
                throw new IllegalStateException("unknown setup step: " + step);
        }
    }

    private SetupState currentSetupState() {
        PlatformImeState platform = observePlatformImeState();
        int enabledLanguageCount = languagePreferences.enabledProfiles().size();
        SetupState state = SetupState.derive(
                platform.enabled,
                platform.selected,
                enabledLanguageCount,
                typingObserved
        );
        if (typingObserved && !state.canTestTyping()) {
            typingObserved = false;
            state = SetupState.derive(
                    platform.enabled,
                    platform.selected,
                    enabledLanguageCount,
                    false
            );
        }
        return state;
    }

    private PlatformImeState observePlatformImeState() {
        InputMethodManager manager = inputMethodManager();
        InputMethodInfo own = null;
        for (InputMethodInfo info : manager.getInputMethodList()) {
            if (isOwnInputMethod(info)) {
                own = info;
                break;
            }
        }
        if (own == null) {
            return new PlatformImeState(false, false);
        }
        boolean enabled = false;
        for (InputMethodInfo info : manager.getEnabledInputMethodList()) {
            if (own.getId().equals(info.getId())) {
                enabled = true;
                break;
            }
        }
        String selectedId = Settings.Secure.getString(
                getContentResolver(),
                Settings.Secure.DEFAULT_INPUT_METHOD
        );
        return new PlatformImeState(enabled, own.getId().equals(selectedId));
    }

    private boolean isOwnInputMethod(InputMethodInfo info) {
        return getPackageName().equals(info.getPackageName())
                && NepaInputMethodService.class.getName().equals(info.getServiceName());
    }

    private InputMethodManager inputMethodManager() {
        return (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
    }

    private LinearLayout card() {
        LinearLayout result = new LinearLayout(this);
        result.setOrientation(LinearLayout.VERTICAL);
        result.setPadding(dp(16), dp(14), dp(16), dp(14));
        result.setBackground(rounded(cardColor, dp(16)));
        return result;
    }

    private Button actionButton(String label) {
        Button button = new Button(this);
        button.setAllCaps(false);
        button.setText(label);
        button.setTextColor(accentColor);
        button.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        button.setGravity(Gravity.CENTER_VERTICAL);
        button.setMinHeight(dp(48));
        button.setBackgroundColor(Color.TRANSPARENT);
        return button;
    }

    private void addText(
            LinearLayout parent,
            String value,
            int size,
            int color,
            int bottomMargin
    ) {
        TextView view = text(value, size, color);
        parent.addView(view, fullWidth(ViewGroup.LayoutParams.WRAP_CONTENT, bottomMargin));
    }

    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextColor(color);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, size);
        return view;
    }

    private LinearLayout.LayoutParams sectionParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        params.setMargins(0, dp(8), 0, dp(16));
        return params;
    }

    private LinearLayout.LayoutParams fullWidth(int height, int bottomMargin) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                height
        );
        params.setMargins(0, 0, 0, dp(bottomMargin));
        return params;
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

    static boolean matchesProfileForTesting(KeyboardProfile profile, String rawQuery) {
        String query = rawQuery.trim().toLowerCase(Locale.ROOT);
        if (query.isEmpty()) {
            return true;
        }
        for (String alias : profile.searchAliases()) {
            if (alias.toLowerCase(Locale.ROOT).contains(query)) {
                return true;
            }
        }
        return profile.id().toLowerCase(Locale.ROOT).contains(query);
    }

    int visibleLanguageProfilesForTesting() {
        return languageAdapter == null ? 0 : languageAdapter.profileCount();
    }

    void setLanguageQueryForTesting(String query) {
        languageQuery = query;
        savedListPosition = 0;
        savedListOffset = 0;
        if (languageAdapter != null) {
            languageAdapter.filter(query);
        }
        if (languageList != null) {
            languageList.setSelection(0);
        }
    }

    String languageQueryForTesting() {
        return languageQuery;
    }

    void setLanguageManagerSelectionForTesting(int position) {
        if (languageList != null) {
            languageList.setSelection(position);
        }
    }

    int languageManagerFirstVisiblePositionForTesting() {
        return languageList == null ? NO_LIST_POSITION : languageList.getFirstVisiblePosition();
    }

    int languageManagerFirstVisibleOffsetForTesting() {
        return languageList == null || languageList.getChildCount() == 0
                ? 0
                : languageList.getChildAt(0).getTop();
    }

    void setLanguageManagerSelectionFromTopForTesting(int position, int offset) {
        if (languageList != null) {
            languageList.setSelectionFromTop(position, offset);
        }
    }

    boolean languageManagerHasStableIdsForTesting() {
        return languageAdapter != null && languageAdapter.hasStableIds();
    }

    int languageManagerViewTypeCountForTesting() {
        return languageAdapter == null ? 0 : languageAdapter.getViewTypeCount();
    }

    int languageManagerSectionCountForTesting(LanguageSection section) {
        return languageAdapter == null ? 0 : languageAdapter.sectionCount(section);
    }

    boolean languageManagerSectionsOrderedForTesting() {
        return languageAdapter != null && languageAdapter.sectionsOrdered();
    }

    boolean languageManagerSectionHeadingsForTesting() {
        return languageAdapter != null
                && languageList != null
                && languageAdapter.sectionHeadingsBound(languageList);
    }

    boolean languageManagerRejectsRepeatedLastDisableForTesting(String profileId) {
        if (languageAdapter == null || languageList == null) {
            return false;
        }
        int position = languageAdapter.positionOfProfile(profileId);
        if (position < 0) {
            return false;
        }
        View row = languageAdapter.getView(position, null, languageList);
        LanguageRowHolder holder = (LanguageRowHolder) row.getTag();
        if (!holder.enabled.isEnabled() || !holder.enabled.isChecked()) {
            return false;
        }
        holder.enabled.performClick();
        boolean firstRejected = holder.enabled.isChecked()
                && languagePreferences.isEnabled(profileId);
        holder.enabled.performClick();
        return firstRejected
                && holder.enabled.isChecked()
                && languagePreferences.isEnabled(profileId);
    }

    boolean languageManagerRecyclesRowsForTesting() {
        if (languageAdapter == null || languageList == null) {
            return false;
        }
        boolean languageRowReused = reusesLanguageRowTypeForTesting();
        boolean headingStateRebound = rebindsLanguageHeadingsForTesting();
        boolean gateAndSwitchStateRebound = rebindsGateAndSwitchForTesting();

        languageAdapter.filter("no-such-language");
        View empty = languageAdapter.getView(0, null, languageList);
        View reusedEmpty = languageAdapter.getView(0, empty, languageList);
        languageAdapter.filter(languageQuery);
        return languageRowReused
                && headingStateRebound
                && gateAndSwitchStateRebound
                && empty == reusedEmpty;
    }

    private boolean reusesLanguageRowTypeForTesting() {
        if (languageAdapter.getCount() < 2
                || languageAdapter.getItemViewType(0) != VIEW_TYPE_LANGUAGE
                || languageAdapter.getItemViewType(1) != VIEW_TYPE_LANGUAGE) {
            return false;
        }
        View firstView = languageAdapter.getView(0, null, languageList);
        View secondView = languageAdapter.getView(1, firstView, languageList);
        LanguageRowHolder holder = (LanguageRowHolder) secondView.getTag();
        KeyboardProfile rebound = (KeyboardProfile) languageAdapter.getItem(1);
        boolean later = !rebound.isAvailable();
        return firstView == secondView
                && holder.name.getText().toString().contains(rebound.nativeName())
                && holder.detail.getText().toString().equals(rebound.detail())
                && holder.enabled.isEnabled() == rebound.isAvailable()
                && holder.enabled.isChecked()
                == (rebound.isAvailable() && languagePreferences.isEnabled(rebound.id()))
                && holder.gate.getVisibility() == (later ? View.VISIBLE : View.GONE)
                && (!later || holder.gate.getText().toString().contains(
                        rebound.blockedDetail()
                ));
    }

    private boolean rebindsLanguageHeadingsForTesting() {
        int sectionStart = -1;
        int languageStart = -1;
        int plainRow = -1;
        for (int position = 0; position < languageAdapter.profileCount(); position++) {
            if (sectionStart == -1 && languageAdapter.startsSection(position)) {
                sectionStart = position;
            }
            if (languageStart == -1
                    && !languageAdapter.startsSection(position)
                    && languageAdapter.startsLanguage(position)) {
                languageStart = position;
            }
            if (plainRow == -1 && !languageAdapter.startsLanguage(position)) {
                plainRow = position;
            }
        }
        if (sectionStart == -1 || languageStart == -1 || plainRow == -1) {
            return false;
        }
        View rebound = languageAdapter.getView(sectionStart, null, languageList);
        LanguageRowHolder holder = (LanguageRowHolder) rebound.getTag();
        if (holder.sectionHeading.getVisibility() != View.VISIBLE
                || holder.languageHeading.getVisibility() != View.VISIBLE) {
            return false;
        }
        rebound = languageAdapter.getView(languageStart, rebound, languageList);
        holder = (LanguageRowHolder) rebound.getTag();
        if (holder.sectionHeading.getVisibility() != View.GONE
                || holder.languageHeading.getVisibility() != View.VISIBLE) {
            return false;
        }
        rebound = languageAdapter.getView(plainRow, rebound, languageList);
        holder = (LanguageRowHolder) rebound.getTag();
        if (holder.sectionHeading.getVisibility() != View.GONE
                || holder.languageHeading.getVisibility() != View.GONE) {
            return false;
        }
        rebound = languageAdapter.getView(sectionStart, rebound, languageList);
        holder = (LanguageRowHolder) rebound.getTag();
        KeyboardProfile profile = (KeyboardProfile) languageAdapter.getItem(sectionStart);
        return holder.sectionHeading.getVisibility() == View.VISIBLE
                && holder.languageHeading.getVisibility() == View.VISIBLE
                && languageSectionTitle(languageAdapter.sectionFor(profile))
                .contentEquals(holder.sectionHeading.getText());
    }

    private boolean rebindsGateAndSwitchForTesting() {
        int selectablePosition = -1;
        int laterPosition = -1;
        for (int position = 0; position < languageAdapter.profileCount(); position++) {
            KeyboardProfile profile = (KeyboardProfile) languageAdapter.getItem(position);
            if (selectablePosition == -1 && profile.isAvailable()) {
                selectablePosition = position;
            }
            if (laterPosition == -1 && !profile.isAvailable()) {
                laterPosition = position;
            }
        }
        if (selectablePosition == -1 || laterPosition == -1) {
            return false;
        }
        View rebound = languageAdapter.getView(selectablePosition, null, languageList);
        LanguageRowHolder holder = (LanguageRowHolder) rebound.getTag();
        if (!holder.enabled.isEnabled() || holder.gate.getVisibility() != View.GONE) {
            return false;
        }
        rebound = languageAdapter.getView(laterPosition, rebound, languageList);
        holder = (LanguageRowHolder) rebound.getTag();
        KeyboardProfile later = (KeyboardProfile) languageAdapter.getItem(laterPosition);
        if (holder.enabled.isEnabled()
                || holder.enabled.isChecked()
                || holder.gate.getVisibility() != View.VISIBLE
                || !holder.gate.getText().toString().contains(later.blockedDetail())) {
            return false;
        }
        rebound = languageAdapter.getView(selectablePosition, rebound, languageList);
        holder = (LanguageRowHolder) rebound.getTag();
        KeyboardProfile selectable = (KeyboardProfile) languageAdapter.getItem(
                selectablePosition
        );
        return holder.enabled.isEnabled()
                && holder.enabled.isChecked() == languagePreferences.isEnabled(selectable.id())
                && holder.gate.getVisibility() == View.GONE
                && holder.gate.getText().length() == 0;
    }

    static long stableProfileIdForTesting(String profileId) {
        long hash = 0xcbf29ce484222325L;
        for (int index = 0; index < profileId.length(); index++) {
            hash ^= profileId.charAt(index);
            hash *= 0x100000001b3L;
        }
        if (hash == EMPTY_ROW_ID || hash == -1L) {
            hash ^= 0x5bd1e9955bd1e995L;
        }
        return hash;
    }

    private static void verifyStableProfileIds() {
        Set<Long> ids = new HashSet<>();
        for (KeyboardProfile profile : LanguageRegistry.all()) {
            if (!ids.add(stableProfileIdForTesting(profile.id()))) {
                throw new IllegalStateException(
                        "generated language-manager stable IDs collide"
                );
            }
        }
    }

    boolean languageManagerScrollsForTesting() {
        return languageList != null
                && languageAdapter != null
                && languageList.getAdapter() != null
                && languageList.getAdapter().getCount() >= languageAdapter.getCount();
    }

    boolean systemBarInsetsAppliedForTesting() {
        return languageList != null
                && systemBarInsets != null
                && languageList.getClipToPadding()
                && systemBarInsets.matches(languageList);
    }

    SetupState setupStateForTesting() {
        return currentSetupState();
    }

    void setSetupTypingTextForTesting(String value) {
        if (setupTypingEditor == null) {
            throw new IllegalStateException("setup typing editor is not rendered");
        }
        setupTypingEditor.setText(value);
    }

    boolean setupTypingTextPersistenceDisabledForTesting() {
        return setupTypingEditor != null
                && !setupTypingEditor.isSaveEnabled()
                && setupTypingEditor.getImportantForAutofill()
                == View.IMPORTANT_FOR_AUTOFILL_NO;
    }

    String setupTypingTextForTesting() {
        return setupTypingEditor == null ? null : setupTypingEditor.getText().toString();
    }

    static SetupState deriveSetupStateForTesting(
            boolean imeEnabled,
            boolean imeSelected,
            int enabledLanguageCount,
            boolean typingObserved
    ) {
        return SetupState.derive(
                imeEnabled,
                imeSelected,
                enabledLanguageCount,
                typingObserved
        );
    }

    enum SetupStep {
        ENABLE_KEYBOARD,
        SELECT_KEYBOARD,
        CHOOSE_LANGUAGES,
        TEST_TYPING,
        COMPLETE
    }

    static final class SetupState {
        private final boolean imeEnabled;
        private final boolean imeSelected;
        private final int enabledLanguageCount;
        private final boolean typingTested;
        private final SetupStep currentStep;

        private SetupState(
                boolean imeEnabled,
                boolean imeSelected,
                int enabledLanguageCount,
                boolean typingTested,
                SetupStep currentStep
        ) {
            this.imeEnabled = imeEnabled;
            this.imeSelected = imeSelected;
            this.enabledLanguageCount = enabledLanguageCount;
            this.typingTested = typingTested;
            this.currentStep = currentStep;
        }

        static SetupState derive(
                boolean imeEnabled,
                boolean imeSelected,
                int enabledLanguageCount,
                boolean typingObserved
        ) {
            int safeLanguageCount = Math.max(0, enabledLanguageCount);
            boolean languagesReady = safeLanguageCount > 0;
            boolean canTestTyping = imeEnabled && imeSelected && languagesReady;
            boolean typingTested = canTestTyping && typingObserved;
            SetupStep currentStep;
            if (!imeEnabled) {
                currentStep = SetupStep.ENABLE_KEYBOARD;
            } else if (!imeSelected) {
                currentStep = SetupStep.SELECT_KEYBOARD;
            } else if (!languagesReady) {
                currentStep = SetupStep.CHOOSE_LANGUAGES;
            } else if (!typingTested) {
                currentStep = SetupStep.TEST_TYPING;
            } else {
                currentStep = SetupStep.COMPLETE;
            }
            return new SetupState(
                    imeEnabled,
                    imeSelected,
                    safeLanguageCount,
                    typingTested,
                    currentStep
            );
        }

        boolean imeEnabled() {
            return imeEnabled;
        }

        boolean imeSelected() {
            return imeSelected;
        }

        int enabledLanguageCount() {
            return enabledLanguageCount;
        }

        boolean languagesReady() {
            return enabledLanguageCount > 0;
        }

        boolean canTestTyping() {
            return imeEnabled && imeSelected && languagesReady();
        }

        boolean typingTested() {
            return typingTested;
        }

        SetupStep currentStep() {
            return currentStep;
        }

        boolean complete() {
            return currentStep == SetupStep.COMPLETE;
        }
    }

    private static final class PlatformImeState {
        private final boolean enabled;
        private final boolean selected;

        PlatformImeState(boolean enabled, boolean selected) {
            this.enabled = enabled;
            this.selected = selected;
        }
    }

    private final class LanguageAdapter extends BaseAdapter {
        private final List<KeyboardProfile> profiles = new ArrayList<>();
        private final Set<String> enabledProfileIds = new HashSet<>();

        LanguageAdapter() {
            for (KeyboardProfile profile : languagePreferences.enabledProfiles()) {
                enabledProfileIds.add(profile.id());
            }
            filter(languageQuery);
        }

        boolean enabledProfileSnapshotMatchesCurrent() {
            Set<String> current = new HashSet<>();
            for (KeyboardProfile profile : languagePreferences.enabledProfiles()) {
                current.add(profile.id());
            }
            return enabledProfileIds.equals(current);
        }

        void filter(String query) {
            profiles.clear();
            for (KeyboardProfile profile : LanguageRegistry.all()) {
                if (matchesProfileForTesting(profile, query)) {
                    profiles.add(profile);
                }
            }
            profiles.sort((left, right) -> {
                int sectionComparison = Integer.compare(
                        sectionFor(left).ordinal(),
                        sectionFor(right).ordinal()
                );
                if (sectionComparison != 0) {
                    return sectionComparison;
                }
                int sortKeyComparison = left.sortKey().compareTo(right.sortKey());
                return sortKeyComparison != 0
                        ? sortKeyComparison
                        : left.id().compareTo(right.id());
            });
            notifyDataSetChanged();
        }

        private LanguageSection sectionFor(KeyboardProfile profile) {
            if (!profile.isAvailable()) {
                return LanguageSection.LATER;
            }
            return enabledProfileIds.contains(profile.id())
                    ? LanguageSection.ENABLED
                    : LanguageSection.AVAILABLE_TO_ENABLE;
        }

        private boolean startsSection(int position) {
            return position == 0
                    || sectionFor(profiles.get(position - 1))
                    != sectionFor(profiles.get(position));
        }

        private boolean startsLanguage(int position) {
            return startsSection(position)
                    || !profiles.get(position - 1).languageId().equals(
                    profiles.get(position).languageId()
            );
        }

        int sectionCount(LanguageSection section) {
            int count = 0;
            for (KeyboardProfile profile : profiles) {
                if (sectionFor(profile) == section) {
                    count++;
                }
            }
            return count;
        }

        boolean sectionsOrdered() {
            int previousOrdinal = -1;
            String previousSortKey = null;
            String previousProfileId = null;
            for (int position = 0; position < profiles.size(); position++) {
                KeyboardProfile profile = profiles.get(position);
                int currentOrdinal = sectionFor(profile).ordinal();
                if (currentOrdinal < previousOrdinal
                        || (currentOrdinal != previousOrdinal && !startsSection(position))) {
                    return false;
                }
                if (currentOrdinal == previousOrdinal && previousSortKey != null) {
                    int sortComparison = previousSortKey.compareTo(profile.sortKey());
                    if (sortComparison > 0
                            || (sortComparison == 0
                            && previousProfileId.compareTo(profile.id()) > 0)) {
                        return false;
                    }
                }
                previousOrdinal = currentOrdinal;
                previousSortKey = profile.sortKey();
                previousProfileId = profile.id();
            }
            return true;
        }

        boolean sectionHeadingsBound(ViewGroup parent) {
            for (int position = 0; position < profiles.size(); position++) {
                if (!startsSection(position)) {
                    continue;
                }
                View row = getView(position, null, parent);
                LanguageRowHolder holder = (LanguageRowHolder) row.getTag();
                if (holder.sectionHeading == null
                        || holder.sectionHeading.getVisibility() != View.VISIBLE
                        || !languageSectionTitle(sectionFor(profiles.get(position)))
                        .contentEquals(holder.sectionHeading.getText())) {
                    return false;
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
                        && !holder.sectionHeading.isAccessibilityHeading()) {
                    return false;
                }
            }
            return true;
        }

        int profileCount() {
            return profiles.size();
        }

        int positionOfProfile(String profileId) {
            for (int position = 0; position < profiles.size(); position++) {
                if (profileId.equals(profiles.get(position).id())) {
                    return position;
                }
            }
            return -1;
        }

        @Override
        public int getCount() {
            return profiles.isEmpty() ? 1 : profiles.size();
        }

        @Override
        public Object getItem(int position) {
            return profiles.isEmpty() ? null : profiles.get(position);
        }

        @Override
        public long getItemId(int position) {
            KeyboardProfile profile = (KeyboardProfile) getItem(position);
            return profile == null ? EMPTY_ROW_ID : stableProfileIdForTesting(profile.id());
        }

        @Override
        public boolean hasStableIds() {
            return true;
        }

        @Override
        public int getViewTypeCount() {
            return 2;
        }

        @Override
        public int getItemViewType(int position) {
            if (profiles.isEmpty()) {
                return VIEW_TYPE_EMPTY;
            }
            return VIEW_TYPE_LANGUAGE;
        }

        @Override
        public View getView(int position, View convertView, ViewGroup parent) {
            if (profiles.isEmpty()) {
                TextView empty = convertView instanceof TextView
                        ? (TextView) convertView
                        : text(getString(R.string.no_languages_found), 16, secondaryTextColor);
                empty.setText(R.string.no_languages_found);
                if (convertView == null) {
                    empty.setPadding(dp(24), dp(20), dp(24), dp(28));
                }
                return empty;
            }
            KeyboardProfile profile = profiles.get(position);
            View row = convertView;
            if (row == null || !(row.getTag() instanceof LanguageRowHolder)) {
                row = createLanguageRow();
            }
            bindLanguageRow(
                    row,
                    profile,
                    sectionFor(profile),
                    startsSection(position),
                    startsLanguage(position)
            );
            return row;
        }
    }

    private static final class LanguageRowHolder {
        final TextView sectionHeading;
        final TextView languageHeading;
        final TextView name;
        final TextView detail;
        final Switch enabled;
        final TextView gate;

        LanguageRowHolder(
                TextView sectionHeading,
                TextView languageHeading,
                TextView name,
                TextView detail,
                Switch enabled,
                TextView gate
        ) {
            this.sectionHeading = sectionHeading;
            this.languageHeading = languageHeading;
            this.name = name;
            this.detail = detail;
            this.enabled = enabled;
            this.gate = gate;
        }
    }
}
