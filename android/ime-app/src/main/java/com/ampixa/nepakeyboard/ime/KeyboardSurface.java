package com.ampixa.nepakeyboard.ime;

import android.annotation.SuppressLint;
import android.content.Context;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Rect;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.SoundEffectConstants;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewParent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

/** Accessible view-backed keyboard surface; every key is an individual control. */
public final class KeyboardSurface extends LinearLayout {
    public interface Listener {
        void onKey(KeySpec key, SpatialKeyStroke stroke);

        void onLanguagePickerRequested(View source);

        /**
         * A key went down. Only preview-eligible keys are reported. Contract harnesses that
         * exercise dispatch alone do not need to observe presses.
         */
        default void onKeyPressed(KeySpec key, View keyView) {
        }

        /** The active press ended, was cancelled, or the surface was detached. */
        default void onKeyReleased() {
        }

        /**
         * A text key with long-press variants was held. Returning true means the variant
         * strip took over the gesture, so the normal tap must not fire.
         */
        default boolean onKeyAlternatesRequested(KeySpec key, View keyView) {
            return false;
        }

        /** The finger moved while the variant strip was open. */
        default void onKeyAlternateDrag(float windowX) {
        }

        /** The finger lifted over the variant strip. Returns true when a variant committed. */
        default boolean onKeyAlternateCommit() {
            return false;
        }

        /** A variant was chosen through its accessibility action rather than by drag. */
        default void onKeyAlternateSelected(KeySpec key, String alternate) {
        }
    }

    private int keyTextColor;
    private int keyColor;
    private int actionKeyColor;
    private int pressedColor;
    private boolean keyBorders = true;
    private final DeleteRepeatController deleteRepeatController;
    private final ScriptTypefaceRegistry scriptTypefaces;
    private Listener listener;
    private KeyboardMetrics metrics;
    private KeyboardLayouts.Layout renderedLayout;
    private boolean hapticsEnabled = KeyboardPreferences.DEFAULT_HAPTICS_ENABLED;
    private boolean soundEnabled = KeyboardPreferences.DEFAULT_SOUND_ENABLED;
    private long nextRenderGeneration;
    private int activeDeletePointerId = MotionEvent.INVALID_POINTER_ID;
    private long testingDeleteDownTime = -1L;

    public KeyboardSurface(Context context) {
        super(context);
        applyThemeColors(KeyboardTheme.resolve(context, KeyboardTheme.SYSTEM_ID));
        scriptTypefaces = new ScriptTypefaceRegistry(context);
        deleteRepeatController = new DeleteRepeatController(
                new DeleteRepeatController.Scheduler() {
                    @Override
                    public void postDelayed(Runnable runnable, long delayMillis) {
                        KeyboardSurface.this.postDelayed(runnable, delayMillis);
                    }

                    @Override
                    public void remove(Runnable runnable) {
                        KeyboardSurface.this.removeCallbacks(runnable);
                    }
                }
        );
        metrics = KeyboardMetrics.forResources(
                context.getResources(),
                KeyboardMetrics.DEFAULT_HEIGHT_PERCENT
        );
        setOrientation(VERTICAL);
        setPadding(dp(4), dp(6), dp(4), dp(8));
    }

    /** Applies a bundled theme and re-renders so no key keeps a stale colour. */
    public void setTheme(KeyboardTheme theme) {
        applyThemeColors(theme);
        if (renderedLayout != null) {
            render(renderedLayout);
        }
    }

    private void applyThemeColors(KeyboardTheme theme) {
        keyTextColor = theme.keyTextColor();
        keyColor = theme.keyColor();
        actionKeyColor = theme.actionKeyColor();
        pressedColor = theme.pressedColor();
        keyBorders = theme.keyBorders();
        setBackgroundColor(theme.surfaceColor());
    }

    int keyColorForTesting() {
        return keyColor;
    }

    boolean keyBordersForTesting() {
        return keyBorders;
    }

    public void setListener(Listener listener) {
        this.listener = listener;
    }

    /** Applies a height preference and re-renders the current layout at the new geometry. */
    public void setHeightPercent(int heightPercent) {
        KeyboardMetrics next = KeyboardMetrics.forResources(
                getContext().getResources(),
                heightPercent
        );
        if (next.rowHeightPx() == metrics.rowHeightPx()) {
            metrics = next;
            return;
        }
        metrics = next;
        if (renderedLayout != null) {
            render(renderedLayout);
        }
    }

    public KeyboardMetrics metrics() {
        return metrics;
    }

    /** Applies the reviewed feedback preferences; both default to off, as in the reference. */
    public void setFeedbackEnabled(boolean sound, boolean haptics) {
        soundEnabled = sound;
        hapticsEnabled = haptics;
    }

    boolean hapticsEnabledForTesting() {
        return hapticsEnabled;
    }

    boolean soundEnabledForTesting() {
        return soundEnabled;
    }

    /** Distinct effects for the action keys, matching the reference's key classes. */
    private static int soundEffectFor(KeySpec.Action action) {
        switch (action) {
            case DELETE:
                return SoundEffectConstants.CLICK;
            case ENTER:
                return SoundEffectConstants.NAVIGATION_DOWN;
            case SPACE:
                return SoundEffectConstants.NAVIGATION_RIGHT;
            default:
                return SoundEffectConstants.CLICK;
        }
    }

    private void notifyKeyPressed(KeySpec key, View keyView) {
        if (listener != null && KeyPreviewOverlay.previewEligible(key)) {
            listener.onKeyPressed(key, keyView);
        }
    }

    private void notifyKeyReleased() {
        if (listener != null) {
            listener.onKeyReleased();
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    public void render(KeyboardLayouts.Layout layout) {
        cancelDeleteRepeat();
        // Re-rendering destroys the pressed key, so its preview must not survive.
        notifyKeyReleased();
        if (nextRenderGeneration == Long.MAX_VALUE) {
            throw new IllegalStateException("keyboard render generation exhausted");
        }
        long renderGeneration = ++nextRenderGeneration;
        renderedLayout = layout;
        removeAllViews();
        for (List<KeySpec> row : visualRows(layout)) {
            LinearLayout rowView = new LinearLayout(getContext());
            rowView.setOrientation(HORIZONTAL);
            rowView.setGravity(Gravity.CENTER);
            int characterInset = characterRowInsetDp(row);
            if (characterInset > 0) {
                rowView.setPadding(dp(characterInset), 0, dp(characterInset), 0);
            }
            LayoutParams rowParams = new LayoutParams(
                    LayoutParams.MATCH_PARENT,
                    metrics.rowHeightPx()
            );
            addView(rowView, rowParams);

            for (KeySpec key : row) {
                TextView keyView = new TextView(getContext());
                keyView.setText(key.label());
                scriptTypefaces.apply(keyView, key.label(), keyView.getTypeface());
                keyView.setTextColor(keyTextColor);
                int baseMaximumTextSizeSp = key.label().codePointCount(0, key.label().length()) > 5
                        ? 12
                        : (key.action() == KeySpec.Action.TEXT ? 21 : 17);
                // The keyboard itself has fixed-height rows. Cap the SP maximum when
                // font scaling grows so labels stay within those rows and key widths.
                float fontScale = Math.max(
                        1f,
                        getResources().getConfiguration().fontScale
                );
                int maximumTextSizeSp = Math.max(
                        6,
                        Math.round(baseMaximumTextSizeSp / fontScale)
                );
                keyView.setTextSize(
                        TypedValue.COMPLEX_UNIT_SP,
                        maximumTextSizeSp
                );
                // A key is always a one-line control. Uniform auto-sizing preserves
                // that contract when the user combines large font and display scales.
                keyView.setSingleLine(true);
                keyView.setAutoSizeTextTypeUniformWithConfiguration(
                        6,
                        maximumTextSizeSp,
                        1,
                        TypedValue.COMPLEX_UNIT_SP
                );
                if (key.action() == KeySpec.Action.SYMBOLS
                        || key.action() == KeySpec.Action.LETTERS) {
                    // These compound labels occupy the narrowest bottom-row key.
                    // Condensing them avoids clipping without abbreviating their meaning.
                    keyView.setTextScaleX(0.62f);
                }
                keyView.setGravity(Gravity.CENTER);
                keyView.setContentDescription(key.contentDescription());
                keyView.setTag(key);
                keyView.setClickable(true);
                keyView.setFocusable(true);
                keyView.setMinHeight(metrics.minimumKeyHeightPx());
                keyView.setBackground(keyBackground(
                        key.action() == KeySpec.Action.TEXT ? keyColor : actionKeyColor
                ));
                applyActionIcon(keyView, key.action());
                applyInputPolicyIcon(keyView, key);
                SpatialKeyStroke[] pendingStroke = new SpatialKeyStroke[1];
                boolean[] alternatesActive = new boolean[1];
                keyView.setOnTouchListener((view, event) -> {
                    if (key.action() == KeySpec.Action.DELETE) {
                        pendingStroke[0] = null;
                        switch (event.getActionMasked()) {
                            case MotionEvent.ACTION_DOWN:
                                if (!deleteRepeatController.isActive()) {
                                    activeDeletePointerId = event.getPointerId(
                                            event.getActionIndex()
                                    );
                                    deleteRepeatController.start(() -> dispatchKey(
                                            view,
                                            key,
                                            null,
                                            renderGeneration
                                    ));
                                }
                                return true;
                            case MotionEvent.ACTION_POINTER_UP:
                                if (event.getPointerId(event.getActionIndex())
                                        == activeDeletePointerId) {
                                    cancelDeleteRepeat();
                                }
                                return true;
                            case MotionEvent.ACTION_MOVE:
                                if (activeDeletePointerId == MotionEvent.INVALID_POINTER_ID
                                        || event.findPointerIndex(activeDeletePointerId) < 0) {
                                    cancelDeleteRepeat();
                                }
                                return true;
                            case MotionEvent.ACTION_UP:
                            case MotionEvent.ACTION_CANCEL:
                                cancelDeleteRepeat();
                                return true;
                            default:
                                return true;
                        }
                    }
                    switch (event.getActionMasked()) {
                        case MotionEvent.ACTION_DOWN:
                            pendingStroke[0] = null;
                            alternatesActive[0] = false;
                            notifyKeyPressed(key, view);
                            break;
                        case MotionEvent.ACTION_MOVE:
                            if (alternatesActive[0] && listener != null) {
                                listener.onKeyAlternateDrag(event.getRawX());
                                return true;
                            }
                            break;
                        case MotionEvent.ACTION_CANCEL:
                            pendingStroke[0] = null;
                            alternatesActive[0] = false;
                            notifyKeyReleased();
                            break;
                        case MotionEvent.ACTION_UP:
                            if (alternatesActive[0]) {
                                alternatesActive[0] = false;
                                pendingStroke[0] = null;
                                // The variant strip owns this gesture; suppress the tap.
                                if (listener != null && listener.onKeyAlternateCommit()) {
                                    return true;
                                }
                                notifyKeyReleased();
                                return true;
                            }
                            notifyKeyReleased();
                            pendingStroke[0] = captureSpatialStroke(
                                    layout,
                                    renderGeneration,
                                    key,
                                    view,
                                    event
                            );
                            SpatialKeyStroke strokeToClear = pendingStroke[0];
                            // View queues PerformClick after this listener returns.
                            // The nested post therefore clears only after that click.
                            view.post(() -> view.post(() -> {
                                if (pendingStroke[0] == strokeToClear) {
                                    pendingStroke[0] = null;
                                }
                            }));
                            break;
                        default:
                            break;
                    }
                    // Preserve TextView click, long-click, focus, and accessibility handling.
                    return false;
                });
                keyView.setOnClickListener(view -> {
                    SpatialKeyStroke stroke = pendingStroke[0];
                    pendingStroke[0] = null;
                    if (key.action() == KeySpec.Action.TEXT && stroke == null) {
                        stroke = nonSpatialStroke(layout, renderGeneration, key);
                    }
                    dispatchKey(view, key, stroke, renderGeneration);
                });
                if (key.hasAlternates()) {
                    keyView.setOnLongClickListener(view -> {
                        if (listener == null || !listener.onKeyAlternatesRequested(key, view)) {
                            return false;
                        }
                        alternatesActive[0] = true;
                        pendingStroke[0] = null;
                        return true;
                    });
                    installAlternateAccessibilityActions(keyView, key);
                } else if (key.holdAction() != null) {
                    keyView.setOnLongClickListener(view -> {
                        // View.performLongClick supplies the standard handled-long-press feedback.
                        if (listener == null) {
                            return false;
                        }
                        switch (key.holdAction()) {
                            case OPEN_LANGUAGE_PICKER:
                                listener.onLanguagePickerRequested(view);
                                return true;
                            default:
                                throw new IllegalStateException(
                                        "unknown key hold action: " + key.holdAction()
                                );
                        }
                    });
                    installHoldAccessibilityAction(keyView, key.holdAction());
                }
                LayoutParams keyParams = new LayoutParams(
                        0,
                        metrics.keyHeightPx(),
                        (float) key.widthUnits()
                );
                int gap = metrics.keyGapPx();
                keyParams.setMargins(gap, gap, gap, gap);
                rowView.addView(keyView, keyParams);
            }
        }
    }

    /**
     * Keeps the reviewed layout artifact semantic while applying conventional phone-keyboard
     * chrome. Shift and Backspace flank the last character row; the globe remains in the bottom
     * row. This prevents a long spacebar label or language glyph from crowding Backspace.
     */
    private List<List<KeySpec>> visualRows(KeyboardLayouts.Layout layout) {
        List<List<KeySpec>> sourceRows = layout.rows();
        if (sourceRows.size() < 2) {
            return sourceRows;
        }
        List<KeySpec> sourceActions = sourceRows.get(sourceRows.size() - 1);
        Map<KeySpec.Action, KeySpec> actions = new EnumMap<>(KeySpec.Action.class);
        for (KeySpec key : sourceActions) {
            if (key.action() == KeySpec.Action.TEXT) {
                return sourceRows;
            }
            actions.put(key.action(), key);
        }
        KeySpec delete = actions.get(KeySpec.Action.DELETE);
        KeySpec space = actions.get(KeySpec.Action.SPACE);
        KeySpec enter = actions.get(KeySpec.Action.ENTER);
        if (delete == null || space == null || enter == null) {
            return sourceRows;
        }

        List<List<KeySpec>> result = new ArrayList<>();
        for (int index = 0; index < sourceRows.size() - 2; index++) {
            result.add(new ArrayList<>(sourceRows.get(index)));
        }
        List<KeySpec> lastCharacters = new ArrayList<>(
                sourceRows.get(sourceRows.size() - 2)
        );

        KeySpec shift = actions.get(KeySpec.Action.SHIFT);
        KeySpec letters = actions.get(KeySpec.Action.LETTERS);
        KeySpec symbols = actions.get(KeySpec.Action.SYMBOLS);
        KeySpec language = actions.get(KeySpec.Action.LANGUAGE);
        List<KeySpec> bottomPunctuation = new ArrayList<>(2);
        if (shift != null) {
            for (int index = 0; index < lastCharacters.size()
                    && bottomPunctuation.size() < 2; ) {
                KeySpec key = lastCharacters.get(index);
                if (isBottomPunctuation(key)) {
                    bottomPunctuation.add(key);
                    lastCharacters.remove(index);
                } else {
                    index++;
                }
            }
        }
        List<KeySpec> bottomUtilities = new ArrayList<>(2);
        for (int index = 0; index < lastCharacters.size(); ) {
            KeySpec key = lastCharacters.get(index);
            if (isJoinerUtility(key)) {
                bottomUtilities.add(key);
                lastCharacters.remove(index);
            } else {
                index++;
            }
        }
        int fixedCharacterRowKeys = (shift == null ? 0 : 1) + 1;
        for (int index = 0;
                lastCharacters.size() + fixedCharacterRowKeys > 10
                        && index < lastCharacters.size(); ) {
            KeySpec key = lastCharacters.get(index);
            if (isBottomPunctuation(key)) {
                bottomPunctuation.add(key);
                lastCharacters.remove(index);
            } else {
                index++;
            }
        }
        boolean needsBalancedRows = lastCharacters.size() + fixedCharacterRowKeys > 10;
        for (List<KeySpec> row : result) {
            needsBalancedRows |= row.size() > 10;
        }
        if (needsBalancedRows) {
            List<KeySpec> allCharacters = new ArrayList<>();
            for (List<KeySpec> row : result) {
                allCharacters.addAll(row);
            }
            allCharacters.addAll(lastCharacters);
            int balancedRowCount = result.size() + 1;
            while (true) {
                int largestRow = (allCharacters.size() + balancedRowCount - 1)
                        / balancedRowCount;
                int smallestRow = allCharacters.size() / balancedRowCount;
                if (largestRow <= 10 && smallestRow + fixedCharacterRowKeys <= 10) {
                    break;
                }
                balancedRowCount++;
            }
            result.clear();
            int cursor = 0;
            int shortRowSize = allCharacters.size() / balancedRowCount;
            int longerRows = allCharacters.size() % balancedRowCount;
            for (int rowIndex = 0; rowIndex < balancedRowCount; rowIndex++) {
                int rowSize = shortRowSize + (rowIndex < longerRows ? 1 : 0);
                List<KeySpec> balanced = new ArrayList<>(
                        allCharacters.subList(cursor, cursor + rowSize)
                );
                cursor += rowSize;
                if (rowIndex == balancedRowCount - 1) {
                    lastCharacters = balanced;
                } else {
                    result.add(balanced);
                }
            }
        }

        List<KeySpec> actionCharacterRow = new ArrayList<>();
        if (shift != null) {
            actionCharacterRow.add(shift);
        }
        actionCharacterRow.addAll(lastCharacters);
        actionCharacterRow.add(delete);
        result.add(actionCharacterRow);

        List<KeySpec> bottom = new ArrayList<>();
        if (letters != null) {
            bottom.add(letters);
        } else if (symbols != null) {
            bottom.add(symbols);
        }
        if (!bottomPunctuation.isEmpty()) {
            bottom.add(bottomPunctuation.get(0));
        }
        bottom.addAll(bottomUtilities);
        if (language != null) {
            bottom.add(language);
        }
        bottom.add(space);
        for (int index = 1; index < bottomPunctuation.size(); index++) {
            bottom.add(bottomPunctuation.get(index));
        }
        bottom.add(enter);
        result.add(bottom);
        return result;
    }

    private static int characterRowInsetDp(List<KeySpec> row) {
        if (row.size() >= 10) {
            return 0;
        }
        for (KeySpec key : row) {
            if (key.action() != KeySpec.Action.TEXT) {
                return 0;
            }
        }
        // Alphabetic rows use a conventional stagger. Sparse numeric rows need
        // a much shallower inset so their three or four keys remain keypad-sized.
        int perMissingKeyDp = row.size() <= 4 ? 6 : 18;
        return (10 - row.size()) * perMissingKeyDp;
    }

    private static boolean isJoinerUtility(KeySpec key) {
        if (key.action() != KeySpec.Action.TEXT || key.inputPolicy() == null) {
            return false;
        }
        switch (key.inputPolicy()) {
            case DEVA_CONJUNCT_JOINER:
            case DEVA_TERMINAL_ZWNJ:
            case NEWA_CONJUNCT_JOINER:
                return true;
            default:
                return false;
        }
    }

    private static boolean isBottomPunctuation(KeySpec key) {
        if (key.action() != KeySpec.Action.TEXT || key.text() == null || key.text().isEmpty()) {
            return false;
        }
        int offset = 0;
        while (offset < key.text().length()) {
            int codePoint = key.text().codePointAt(offset);
            int type = Character.getType(codePoint);
            if (type != Character.CONNECTOR_PUNCTUATION
                    && type != Character.DASH_PUNCTUATION
                    && type != Character.START_PUNCTUATION
                    && type != Character.END_PUNCTUATION
                    && type != Character.INITIAL_QUOTE_PUNCTUATION
                    && type != Character.FINAL_QUOTE_PUNCTUATION
                    && type != Character.OTHER_PUNCTUATION) {
                return false;
            }
            offset += Character.charCount(codePoint);
        }
        return true;
    }

    private void applyActionIcon(TextView view, KeySpec.Action action) {
        int drawableId;
        switch (action) {
            case LANGUAGE:
                drawableId = R.drawable.ic_language_switch_24;
                break;
            case DELETE:
                drawableId = R.drawable.ic_backspace_24;
                break;
            case SHIFT:
                drawableId = R.drawable.ic_shift_24;
                break;
            case ENTER:
                drawableId = R.drawable.ic_enter_24;
                break;
            default:
                return;
        }
        Drawable icon = getContext().getDrawable(drawableId);
        if (icon == null) {
            return;
        }
        int size = dp(22);
        icon.setBounds(0, 0, size, size);
        icon.setTint(keyTextColor);
        view.setText("");
        view.setCompoundDrawables(icon, null, null, null);
    }

    private void applyInputPolicyIcon(TextView view, KeySpec key) {
        if (!isJoinerUtility(key) || key.text() == null || key.text().isEmpty()) {
            return;
        }
        int codePoint = key.text().codePointAt(0);
        int drawableId;
        if (codePoint == 0x200D) {
            drawableId = R.drawable.ic_joiner_24;
        } else if (codePoint == 0x200C) {
            drawableId = R.drawable.ic_non_joiner_24;
        } else {
            return;
        }
        Drawable icon = getContext().getDrawable(drawableId);
        if (icon == null) {
            return;
        }
        int size = dp(20);
        icon.setBounds(0, 0, size, size);
        icon.setTint(keyTextColor);
        view.setText("");
        view.setCompoundDrawables(icon, null, null, null);
    }

    private void dispatchKey(
            View view,
            KeySpec key,
            SpatialKeyStroke stroke,
            long renderGeneration
    ) {
        if (renderGeneration != nextRenderGeneration) {
            return;
        }
        if (hapticsEnabled) {
            view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP);
        }
        if (soundEnabled) {
            view.playSoundEffect(soundEffectFor(key.action()));
        }
        if (listener != null) {
            listener.onKey(key, stroke);
        }
    }

    @Override
    protected void onDetachedFromWindow() {
        cancelDeleteRepeat();
        // A detached surface must never leave a key preview behind.
        notifyKeyReleased();
        super.onDetachedFromWindow();
    }

    void cancelDeleteRepeat() {
        activeDeletePointerId = MotionEvent.INVALID_POINTER_ID;
        testingDeleteDownTime = -1L;
        deleteRepeatController.stop();
    }

    private SpatialKeyStroke captureSpatialStroke(
            KeyboardLayouts.Layout layout,
            long renderGeneration,
            KeySpec selected,
            View selectedView,
            MotionEvent event
    ) {
        if (renderGeneration != nextRenderGeneration
                || selected.action() != KeySpec.Action.TEXT
                || layout.layoutRevision() < 1
                || layout.layoutSourceSha256() == null
                || getWidth() <= 0
                || getHeight() <= 0) {
            return null;
        }
        List<KeyboardGeometry.KeyBounds> keys = new ArrayList<>();
        for (int rowIndex = 0; rowIndex < getChildCount(); rowIndex++) {
            View row = getChildAt(rowIndex);
            if (!(row instanceof LinearLayout)) {
                continue;
            }
            LinearLayout rowView = (LinearLayout) row;
            for (int keyIndex = 0; keyIndex < rowView.getChildCount(); keyIndex++) {
                View candidateView = rowView.getChildAt(keyIndex);
                Object tag = candidateView.getTag();
                if (!(tag instanceof KeySpec)) {
                    continue;
                }
                KeySpec candidate = (KeySpec) tag;
                if (candidate.action() != KeySpec.Action.TEXT
                        || candidateView.getWidth() <= 0
                        || candidateView.getHeight() <= 0) {
                    continue;
                }
                int leftPixels = descendantOffset(candidateView, true);
                int topPixels = descendantOffset(candidateView, false);
                if (leftPixels == Integer.MIN_VALUE || topPixels == Integer.MIN_VALUE) {
                    continue;
                }
                int left = normalizeCoordinate(leftPixels, getWidth());
                int top = normalizeCoordinate(topPixels, getHeight());
                int right = normalizeCoordinate(
                        leftPixels + candidateView.getWidth(),
                        getWidth()
                );
                int bottom = normalizeCoordinate(
                        topPixels + candidateView.getHeight(),
                        getHeight()
                );
                keys.add(new KeyboardGeometry.KeyBounds(
                        candidate.keyId(),
                        candidate.text(),
                        candidate.inputPolicy(),
                        left,
                        top,
                        right,
                        bottom
                ));
            }
        }
        if (keys.isEmpty()) {
            return null;
        }
        KeyboardGeometry geometry = new KeyboardGeometry(
                layout.sourceLayoutId(),
                layout.layoutRevision(),
                layout.layoutSourceSha256(),
                renderGeneration,
                keys
        );
        int selectedLeft = descendantOffset(selectedView, true);
        int selectedTop = descendantOffset(selectedView, false);
        if (selectedLeft == Integer.MIN_VALUE || selectedTop == Integer.MIN_VALUE) {
            return null;
        }
        int x = normalizeCoordinate(
                selectedLeft + (double) event.getX(),
                getWidth()
        );
        int y = normalizeCoordinate(
                selectedTop + (double) event.getY(),
                getHeight()
        );
        return SpatialKeyStroke.spatial(
                geometry,
                selected.keyId(),
                selected.text(),
                selected.inputPolicy(),
                x,
                y
        );
    }

    private static SpatialKeyStroke nonSpatialStroke(
            KeyboardLayouts.Layout layout,
            long renderGeneration,
            KeySpec key
    ) {
        if (key.action() != KeySpec.Action.TEXT
                || layout.layoutRevision() < 1
                || layout.layoutSourceSha256() == null) {
            return null;
        }
        return SpatialKeyStroke.nonSpatial(
                layout.sourceLayoutId(),
                layout.layoutRevision(),
                layout.layoutSourceSha256(),
                renderGeneration,
                key.keyId(),
                key.text(),
                key.inputPolicy()
        );
    }

    /**
     * Exposes each long-press variant as its own accessibility action, so a screen-reader
     * user can reach variants without performing a touch-and-drag gesture.
     */
    private void installAlternateAccessibilityActions(View keyView, KeySpec key) {
        keyView.setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
        keyView.setAccessibilityDelegate(new View.AccessibilityDelegate() {
            @Override
            public void onInitializeAccessibilityNodeInfo(
                    View host,
                    AccessibilityNodeInfo info
            ) {
                super.onInitializeAccessibilityNodeInfo(host, info);
                info.removeAction(
                        AccessibilityNodeInfo.AccessibilityAction.ACTION_LONG_CLICK
                );
                for (int index = 0; index < key.alternates().size(); index++) {
                    info.addAction(new AccessibilityNodeInfo.AccessibilityAction(
                            alternateActionId(index),
                            key.alternates().get(index)
                    ));
                }
            }

            @Override
            public boolean performAccessibilityAction(View host, int action, Bundle arguments) {
                for (int index = 0; index < key.alternates().size(); index++) {
                    if (action == alternateActionId(index)) {
                        dispatchAlternate(host, key, key.alternates().get(index));
                        return true;
                    }
                }
                return super.performAccessibilityAction(host, action, arguments);
            }
        });
    }

    private static int alternateActionId(int index) {
        return ALTERNATE_ACTION_IDS[index];
    }

    private void dispatchAlternate(View view, KeySpec key, String alternate) {
        if (listener != null) {
            listener.onKeyAlternateSelected(key, alternate);
        }
    }

    private static final int[] ALTERNATE_ACTION_IDS = {
            R.id.key_alternate_0,
            R.id.key_alternate_1,
            R.id.key_alternate_2,
            R.id.key_alternate_3,
            R.id.key_alternate_4,
            R.id.key_alternate_5,
            R.id.key_alternate_6,
            R.id.key_alternate_7,
    };

    private void installHoldAccessibilityAction(
            View keyView,
            KeySpec.HoldAction holdAction
    ) {
        keyView.setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
        switch (holdAction) {
            case OPEN_LANGUAGE_PICKER:
                CharSequence label = getContext().getString(R.string.choose_language);
                keyView.setAccessibilityDelegate(new View.AccessibilityDelegate() {
                    @Override
                    public void onInitializeAccessibilityNodeInfo(
                            View host,
                            AccessibilityNodeInfo info
                    ) {
                        super.onInitializeAccessibilityNodeInfo(host, info);
                        info.removeAction(
                                AccessibilityNodeInfo.AccessibilityAction.ACTION_LONG_CLICK
                        );
                        info.addAction(new AccessibilityNodeInfo.AccessibilityAction(
                                AccessibilityNodeInfo.AccessibilityAction.ACTION_LONG_CLICK.getId(),
                                label
                        ));
                    }

                    @Override
                    public boolean performAccessibilityAction(
                            View host,
                            int action,
                            Bundle arguments
                    ) {
                        if (action
                                == AccessibilityNodeInfo.AccessibilityAction.ACTION_LONG_CLICK
                                .getId()) {
                            return host.performLongClick();
                        }
                        return super.performAccessibilityAction(host, action, arguments);
                    }
                });
                return;
            default:
                throw new IllegalStateException("unknown key hold action: " + holdAction);
        }
    }

    private static int normalizeCoordinate(double value, int extent) {
        if (extent <= 0) {
            throw new IllegalArgumentException("keyboard extent must be positive");
        }
        long normalized = Math.round(
                (value * KeyboardGeometry.COORDINATE_SCALE) / extent
        );
        return (int) Math.max(0L, Math.min(KeyboardGeometry.COORDINATE_SCALE, normalized));
    }

    /** Returns a descendant's local offset without consulting global/window coordinates. */
    private int descendantOffset(View descendant, boolean horizontal) {
        int offset = 0;
        View current = descendant;
        while (current != this) {
            offset += horizontal ? current.getLeft() : current.getTop();
            ViewParent parent = current.getParent();
            if (!(parent instanceof View)) {
                return Integer.MIN_VALUE;
            }
            View parentView = (View) parent;
            offset -= horizontal ? parentView.getScrollX() : parentView.getScrollY();
            current = parentView;
        }
        return offset;
    }

    boolean performTextKeyForTesting(String text) {
        for (int rowIndex = 0; rowIndex < getChildCount(); rowIndex++) {
            View row = getChildAt(rowIndex);
            if (!(row instanceof LinearLayout)) {
                continue;
            }
            LinearLayout rowView = (LinearLayout) row;
            for (int keyIndex = 0; keyIndex < rowView.getChildCount(); keyIndex++) {
                View keyView = rowView.getChildAt(keyIndex);
                Object tag = keyView.getTag();
                if (tag instanceof KeySpec && text.equals(((KeySpec) tag).text())) {
                    return keyView.performClick();
                }
            }
        }
        return false;
    }

    /** Dispatches a real down/up pair through one laid-out text key. */
    boolean performTextKeyTouchForTesting(
            String text,
            float horizontalFraction,
            float verticalFraction
    ) {
        return performTextKeyDriftForTesting(
                text,
                horizontalFraction,
                horizontalFraction,
                verticalFraction
        );
    }

    /** Dispatches a real down/up pair whose release may cross a key boundary. */
    boolean performTextKeyDriftForTesting(
            String text,
            float downHorizontalFraction,
            float upHorizontalFraction,
            float verticalFraction
    ) {
        if (!Float.isFinite(downHorizontalFraction)
                || !Float.isFinite(upHorizontalFraction)
                || !Float.isFinite(verticalFraction)
                || downHorizontalFraction < 0f
                || downHorizontalFraction > 1f
                || upHorizontalFraction < -0.25f
                || upHorizontalFraction > 1.25f
                || verticalFraction < 0f
                || verticalFraction > 1f) {
            throw new IllegalArgumentException(
                    "touch fractions must be finite and inside the bounded test gesture"
            );
        }
        View keyView = textKeyViewForTesting(text);
        if (keyView == null || keyView.getWidth() <= 0 || keyView.getHeight() <= 0) {
            return false;
        }
        float downX = Math.min(
                keyView.getWidth() - 1f,
                Math.max(0f, downHorizontalFraction * keyView.getWidth())
        );
        float upX = upHorizontalFraction * keyView.getWidth();
        float y = Math.min(
                keyView.getHeight() - 1f,
                Math.max(0f, verticalFraction * keyView.getHeight())
        );
        long downTime = SystemClock.uptimeMillis();
        MotionEvent down = MotionEvent.obtain(
                downTime,
                downTime,
                MotionEvent.ACTION_DOWN,
                downX,
                y,
                0
        );
        MotionEvent up = MotionEvent.obtain(
                downTime,
                downTime + 1L,
                MotionEvent.ACTION_UP,
                upX,
                y,
                0
        );
        try {
            boolean downHandled = keyView.dispatchTouchEvent(down);
            boolean upHandled = keyView.dispatchTouchEvent(up);
            return downHandled && upHandled;
        } finally {
            down.recycle();
            up.recycle();
        }
    }

    private View textKeyViewForTesting(String text) {
        for (int rowIndex = 0; rowIndex < getChildCount(); rowIndex++) {
            View row = getChildAt(rowIndex);
            if (!(row instanceof LinearLayout)) {
                continue;
            }
            LinearLayout rowView = (LinearLayout) row;
            for (int keyIndex = 0; keyIndex < rowView.getChildCount(); keyIndex++) {
                View keyView = rowView.getChildAt(keyIndex);
                Object tag = keyView.getTag();
                if (tag instanceof KeySpec
                        && ((KeySpec) tag).action() == KeySpec.Action.TEXT
                        && text.equals(((KeySpec) tag).text())) {
                    return keyView;
                }
            }
        }
        return null;
    }

    boolean textKeyUsesBundledNewaTypefaceForTesting(String text) {
        View keyView = textKeyViewForTesting(text);
        return keyView instanceof TextView
                && scriptTypefaces.usesBundledNewa((TextView) keyView);
    }

    boolean allVisibleNewaKeysUseBundledTypefaceForTesting() {
        boolean sawNewa = false;
        for (int rowIndex = 0; rowIndex < getChildCount(); rowIndex++) {
            View row = getChildAt(rowIndex);
            if (!(row instanceof LinearLayout)) {
                continue;
            }
            LinearLayout rowView = (LinearLayout) row;
            for (int keyIndex = 0; keyIndex < rowView.getChildCount(); keyIndex++) {
                View keyView = rowView.getChildAt(keyIndex);
                Object tag = keyView.getTag();
                if (!(tag instanceof KeySpec)
                        || !ScriptTypefaceRegistry.containsNewa(((KeySpec) tag).label())) {
                    continue;
                }
                sawNewa = true;
                if (!(keyView instanceof TextView)
                        || !scriptTypefaces.usesBundledNewa((TextView) keyView)) {
                    return false;
                }
            }
        }
        return sawNewa;
    }

    /** Fires the long-press path for a key, as a real hold would. */
    boolean performLongPressForTesting(String keyId) {
        View keyView = keyViewForTesting(keyId);
        return keyView != null && keyView.isLongClickable() && keyView.performLongClick();
    }

    boolean performKeyIdForTesting(String keyId) {
        View keyView = keyViewForTesting(keyId);
        return keyView != null && keyView.performClick();
    }

    /** Dispatches a short real touch through the first rendered action key. */
    boolean performActionKeyTouchForTesting(KeySpec.Action action) {
        if (!beginActionKeyTouchForTesting(action)) {
            return false;
        }
        return finishActionKeyTouchForTesting(action, false);
    }

    boolean beginActionKeyTouchForTesting(KeySpec.Action action) {
        return dispatchActionTouchForTesting(action, MotionEvent.ACTION_DOWN);
    }

    boolean finishActionKeyTouchForTesting(KeySpec.Action action, boolean cancel) {
        return dispatchActionTouchForTesting(
                action,
                cancel ? MotionEvent.ACTION_CANCEL : MotionEvent.ACTION_UP
        );
    }

    boolean releaseDeleteOwnerWithSecondaryPointerForTesting() {
        return releaseDeletePointerWithSecondaryPointerForTesting(0);
    }

    boolean releaseDeleteNonOwnerWithSecondaryPointerForTesting() {
        return releaseDeletePointerWithSecondaryPointerForTesting(1);
    }

    private boolean releaseDeletePointerWithSecondaryPointerForTesting(int releasedIndex) {
        View keyView = actionKeyViewForTesting(KeySpec.Action.DELETE);
        if (keyView == null || releasedIndex < 0 || releasedIndex > 1) {
            return false;
        }
        MotionEvent.PointerProperties[] properties = new MotionEvent.PointerProperties[2];
        MotionEvent.PointerCoords[] coordinates = new MotionEvent.PointerCoords[2];
        for (int index = 0; index < 2; index++) {
            MotionEvent.PointerProperties pointer = new MotionEvent.PointerProperties();
            pointer.id = index;
            pointer.toolType = MotionEvent.TOOL_TYPE_FINGER;
            properties[index] = pointer;
            MotionEvent.PointerCoords coordinate = new MotionEvent.PointerCoords();
            coordinate.x = index + 1f;
            coordinate.y = 1f;
            coordinate.pressure = 1f;
            coordinate.size = 1f;
            coordinates[index] = coordinate;
        }
        long now = SystemClock.uptimeMillis();
        long downTime = testingDeleteDownTime;
        if (downTime < 0L) {
            return false;
        }
        MotionEvent pointerDown = MotionEvent.obtain(
                downTime,
                now,
                MotionEvent.ACTION_POINTER_DOWN
                        | (1 << MotionEvent.ACTION_POINTER_INDEX_SHIFT),
                2,
                properties,
                coordinates,
                0,
                0,
                1f,
                1f,
                0,
                0,
                0,
                0
        );
        MotionEvent pointerUp = MotionEvent.obtain(
                downTime,
                now + 1L,
                MotionEvent.ACTION_POINTER_UP
                        | (releasedIndex << MotionEvent.ACTION_POINTER_INDEX_SHIFT),
                2,
                properties,
                coordinates,
                0,
                0,
                1f,
                1f,
                0,
                0,
                0,
                0
        );
        MotionEvent remainingPointerUp = null;
        if (releasedIndex == 0) {
            MotionEvent.PointerProperties[] remainingProperties = {
                    properties[1]
            };
            MotionEvent.PointerCoords[] remainingCoordinates = {
                    coordinates[1]
            };
            remainingPointerUp = MotionEvent.obtain(
                    downTime,
                    now + 2L,
                    MotionEvent.ACTION_UP,
                    1,
                    remainingProperties,
                    remainingCoordinates,
                    0,
                    0,
                    1f,
                    1f,
                    0,
                    0,
                    0,
                    0
            );
        }
        try {
            boolean downHandled = keyView.dispatchTouchEvent(pointerDown);
            boolean upHandled = keyView.dispatchTouchEvent(pointerUp);
            boolean remainingHandled = remainingPointerUp == null
                    || keyView.dispatchTouchEvent(remainingPointerUp);
            return downHandled && upHandled && remainingHandled;
        } finally {
            pointerDown.recycle();
            pointerUp.recycle();
            if (remainingPointerUp != null) {
                remainingPointerUp.recycle();
            }
        }
    }

    private boolean dispatchActionTouchForTesting(KeySpec.Action action, int eventAction) {
        View keyView = actionKeyViewForTesting(action);
        if (keyView == null) {
            return false;
        }
        long eventTime = SystemClock.uptimeMillis();
        long downTime = eventTime;
        if (action == KeySpec.Action.DELETE) {
            if (eventAction == MotionEvent.ACTION_DOWN) {
                testingDeleteDownTime = eventTime;
            } else if (testingDeleteDownTime >= 0L) {
                downTime = testingDeleteDownTime;
            }
        }
        MotionEvent event = MotionEvent.obtain(
                downTime,
                eventTime,
                eventAction,
                1f,
                1f,
                0
        );
        try {
            return keyView.dispatchTouchEvent(event);
        } finally {
            event.recycle();
        }
    }

    boolean deleteRepeatActiveForTesting() {
        return deleteRepeatController.isActive();
    }

    long deleteDispatchCountForTesting() {
        return deleteRepeatController.totalDispatchCount();
    }

    boolean visualGeometryContractForTesting() {
        if (getWidth() <= 0
                || getHeight() <= 0
                || getPaddingLeft() < dp(4)
                || getPaddingRight() < dp(4)
                || getPaddingTop() < dp(6)
                || getPaddingBottom() < dp(8)) {
            return false;
        }
        for (int rowIndex = 0; rowIndex < getChildCount(); rowIndex++) {
            View row = getChildAt(rowIndex);
            if (!(row instanceof LinearLayout)) {
                return false;
            }
            LinearLayout rowView = (LinearLayout) row;
            if (rowView.getChildCount() > 10) {
                return false;
            }
            int previousRight = Integer.MIN_VALUE;
            for (int keyIndex = 0; keyIndex < rowView.getChildCount(); keyIndex++) {
                View key = rowView.getChildAt(keyIndex);
                if (key.getWidth() <= 0
                        || key.getHeight() < metrics.minimumKeyHeightPx()
                        || key.getLeft() < 0
                        || key.getRight() > rowView.getWidth()
                        || key.getTop() < 0
                        || key.getBottom() > rowView.getHeight()
                        || (previousRight != Integer.MIN_VALUE && key.getLeft() < previousRight)) {
                    android.util.Log.e(
                            "NepaGeometry",
                            "key bounds failed at row " + rowIndex + ", key " + keyIndex
                    );
                    return false;
                }
                if (!(key instanceof TextView)) {
                    android.util.Log.e("NepaGeometry", "non-text key view");
                    return false;
                }
                TextView keyLabel = (TextView) key;
                if (keyLabel.getMaxLines() != 1
                        || keyLabel.getAutoSizeTextType()
                        != TextView.AUTO_SIZE_TEXT_TYPE_UNIFORM) {
                    android.util.Log.e(
                            "NepaGeometry",
                            "single-line auto-size failed for " + keyLabel.getText()
                    );
                    return false;
                }
                if (keyLabel.getText().length() > 0
                        && (keyLabel.getLayout() == null
                        || keyLabel.getLayout().getLineCount() != 1
                        || keyLabel.getLayout().getLineWidth(0)
                        > keyLabel.getWidth()
                        - keyLabel.getCompoundPaddingLeft()
                        - keyLabel.getCompoundPaddingRight() + 1f)) {
                    android.util.Log.e(
                            "NepaGeometry",
                            "label overflow for " + keyLabel.getText()
                                    + ": line=" + (keyLabel.getLayout() == null
                                    ? -1f
                                    : keyLabel.getLayout().getLineWidth(0))
                                    + ", content=" + (keyLabel.getWidth()
                                    - keyLabel.getCompoundPaddingLeft()
                                    - keyLabel.getCompoundPaddingRight())
                                    + ", size=" + keyLabel.getTextSize()
                                    + ", scaleX=" + keyLabel.getTextScaleX()
                    );
                    return false;
                }
                Object tag = key.getTag();
                if (tag instanceof KeySpec && isJoinerUtility((KeySpec) tag)) {
                    TextView joinerView = (TextView) key;
                    if (joinerView.getText().length() != 0
                            || joinerView.getCompoundDrawables()[0] == null
                            || indexOfChild(rowView) != getChildCount() - 1) {
                        return false;
                    }
                }
                previousRight = key.getRight();
            }
        }

        View delete = actionKeyViewForTesting(KeySpec.Action.DELETE);
        if (delete == null || !(delete.getParent() instanceof LinearLayout)) {
            return false;
        }
        LinearLayout deleteRow = (LinearLayout) delete.getParent();
        if (deleteRow.getChildAt(deleteRow.getChildCount() - 1) != delete
                || indexOfChild(deleteRow) != getChildCount() - 2) {
            return false;
        }
        View language = actionKeyViewForTesting(KeySpec.Action.LANGUAGE);
        if (language == null) {
            return true;
        }
        if (!(language.getParent() instanceof LinearLayout)
                || indexOfChild((View) language.getParent()) != getChildCount() - 1
                || language.getParent() == delete.getParent()) {
            return false;
        }
        Rect deleteBounds = boundsInSurface(delete);
        Rect languageBounds = boundsInSurface(language);
        return deleteBounds != null
                && languageBounds != null
                && !Rect.intersects(deleteBounds, languageBounds)
                && deleteBounds.bottom <= languageBounds.top;
    }

    int actionRowIndexForTesting(KeySpec.Action action) {
        View key = actionKeyViewForTesting(action);
        if (key == null || !(key.getParent() instanceof View)) {
            return -1;
        }
        return indexOfChild((View) key.getParent());
    }

    private Rect boundsInSurface(View descendant) {
        int left = descendantOffset(descendant, true);
        int top = descendantOffset(descendant, false);
        if (left == Integer.MIN_VALUE || top == Integer.MIN_VALUE) {
            return null;
        }
        return new Rect(left, top, left + descendant.getWidth(), top + descendant.getHeight());
    }

    private View actionKeyViewForTesting(KeySpec.Action action) {
        for (int rowIndex = 0; rowIndex < getChildCount(); rowIndex++) {
            View row = getChildAt(rowIndex);
            if (!(row instanceof LinearLayout)) {
                continue;
            }
            LinearLayout rowView = (LinearLayout) row;
            for (int keyIndex = 0; keyIndex < rowView.getChildCount(); keyIndex++) {
                View keyView = rowView.getChildAt(keyIndex);
                Object tag = keyView.getTag();
                if (tag instanceof KeySpec && ((KeySpec) tag).action() == action) {
                    return keyView;
                }
            }
        }
        return null;
    }

    boolean pickerHoldAccessibilityActionMatchesForTesting(
            String keyId,
            CharSequence expectedLabel
    ) {
        View keyView = keyViewForTesting(keyId);
        if (keyView == null || expectedLabel == null || !keyView.isLongClickable()) {
            return false;
        }
        AccessibilityNodeInfo info = keyView.createAccessibilityNodeInfo();
        try {
            int matchingIdCount = 0;
            boolean labelMatches = false;
            for (AccessibilityNodeInfo.AccessibilityAction action : info.getActionList()) {
                if (action.getId()
                        == AccessibilityNodeInfo.AccessibilityAction.ACTION_LONG_CLICK.getId()) {
                    matchingIdCount++;
                    labelMatches = expectedLabel.toString().contentEquals(action.getLabel());
                }
            }
            return keyView.isImportantForAccessibility()
                    && info.isLongClickable()
                    && matchingIdCount == 1
                    && labelMatches;
        } finally {
            info.recycle();
        }
    }

    boolean longClickAccessibilityActionAbsentForTesting(String keyId) {
        View keyView = keyViewForTesting(keyId);
        if (keyView == null || keyView.isLongClickable()) {
            return false;
        }
        AccessibilityNodeInfo info = keyView.createAccessibilityNodeInfo();
        try {
            for (AccessibilityNodeInfo.AccessibilityAction action : info.getActionList()) {
                if (action.getId()
                        == AccessibilityNodeInfo.AccessibilityAction.ACTION_LONG_CLICK.getId()) {
                    return false;
                }
            }
            return true;
        } finally {
            info.recycle();
        }
    }

    CharSequence keyContentDescriptionForTesting(String keyId) {
        View keyView = keyViewForTesting(keyId);
        if (keyView == null) {
            return null;
        }
        AccessibilityNodeInfo info = keyView.createAccessibilityNodeInfo();
        try {
            CharSequence description = info.getContentDescription();
            return description == null ? null : description.toString();
        } finally {
            info.recycle();
        }
    }

    boolean performPickerHoldAccessibilityActionForTesting(String keyId) {
        View keyView = keyViewForTesting(keyId);
        return keyView != null && keyView.performAccessibilityAction(
                AccessibilityNodeInfo.AccessibilityAction.ACTION_LONG_CLICK.getId(),
                null
        );
    }

    boolean requestKeyInputFocusForTesting(String keyId) {
        View keyView = keyViewForTesting(keyId);
        return keyView != null && keyView.requestFocusFromTouch() && keyView.hasFocus();
    }

    boolean keyHasInputFocusForTesting(String keyId) {
        View keyView = keyViewForTesting(keyId);
        return keyView != null && keyView.hasFocus();
    }

    boolean clearKeyInputFocusForTesting(String keyId) {
        View keyView = keyViewForTesting(keyId);
        if (keyView == null) {
            return false;
        }
        keyView.clearFocus();
        return !keyView.hasFocus();
    }

    private View keyViewForTesting(String keyId) {
        for (int rowIndex = 0; rowIndex < getChildCount(); rowIndex++) {
            View row = getChildAt(rowIndex);
            if (!(row instanceof LinearLayout)) {
                continue;
            }
            LinearLayout rowView = (LinearLayout) row;
            for (int keyIndex = 0; keyIndex < rowView.getChildCount(); keyIndex++) {
                View keyView = rowView.getChildAt(keyIndex);
                Object tag = keyView.getTag();
                if (tag instanceof KeySpec && keyId.equals(((KeySpec) tag).keyId())) {
                    return keyView;
                }
            }
        }
        return null;
    }

    private StateListDrawable keyBackground(int normalColor) {
        StateListDrawable states = new StateListDrawable();
        states.addState(new int[]{android.R.attr.state_pressed}, rounded(pressedColor));
        states.addState(new int[]{}, rounded(normalColor));
        return states;
    }

    private GradientDrawable rounded(int color) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(7));
        if (!keyBorders) {
            // Borderless themes still need a hairline so adjacent keys stay separable.
            drawable.setStroke(Math.max(1, dp(1) / 2), color);
        }
        return drawable;
    }

    private int dp(int value) {
        return Math.round(TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP,
                value,
                getResources().getDisplayMetrics()
        ));
    }
}
