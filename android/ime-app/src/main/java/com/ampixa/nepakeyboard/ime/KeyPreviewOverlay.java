package com.ampixa.nepakeyboard.ime;

import android.content.Context;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.TextView;

import java.util.Objects;

/**
 * In-window key preview.
 *
 * <p>Lives inside the input view instead of a separate window, so it can never outlive the
 * IME window token and is dismissed deterministically on every lifecycle boundary.
 */
public final class KeyPreviewOverlay extends FrameLayout {
    /** Reviewed reference preview metrics. */
    static final int PREVIEW_TEXT_SIZE_SP = 22;
    static final int PREVIEW_MIN_WIDTH_DP = 32;
    static final int PREVIEW_VERTICAL_OFFSET_DP = 16;

    private final TextView previewLabel;
    private final android.widget.LinearLayout alternateStrip;
    private final ScriptTypefaceRegistry scriptTypefaces;
    private final int previewMinWidthPx;
    private final int previewOffsetPx;
    private final boolean darkTheme;
    private String shownKeyId;
    private KeySpec shownKey;
    private java.util.List<String> shownAlternates = java.util.Collections.emptyList();
    private int highlightedAlternate = -1;
    private AlternateListener alternateListener;

    /** Receives the variant chosen by lifting a finger over it. */
    public interface AlternateListener {
        void onAlternateSelected(KeySpec key, String alternate);
    }

    public KeyPreviewOverlay(Context context) {
        super(context);
        boolean dark = (context.getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        darkTheme = dark;
        scriptTypefaces = new ScriptTypefaceRegistry(context);
        previewMinWidthPx = dp(PREVIEW_MIN_WIDTH_DP);
        previewOffsetPx = dp(PREVIEW_VERTICAL_OFFSET_DP);

        setClickable(false);
        setFocusable(false);
        // The overlay is decorative; the pressed key already carries the accessible label.
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        setVisibility(GONE);

        previewLabel = new TextView(context);
        previewLabel.setTextSize(TypedValue.COMPLEX_UNIT_SP, PREVIEW_TEXT_SIZE_SP);
        previewLabel.setTextColor(dark ? Color.rgb(244, 242, 248) : Color.rgb(34, 32, 38));
        previewLabel.setGravity(Gravity.CENTER);
        previewLabel.setMinWidth(previewMinWidthPx);
        previewLabel.setPadding(dp(10), dp(6), dp(10), dp(6));
        GradientDrawable background = new GradientDrawable();
        background.setColor(dark ? Color.rgb(66, 63, 74) : Color.rgb(255, 255, 255));
        background.setCornerRadius(dp(8));
        background.setStroke(
                Math.max(1, dp(1)),
                dark ? Color.rgb(96, 92, 106) : Color.rgb(203, 199, 214)
        );
        previewLabel.setBackground(background);
        addView(previewLabel, new LayoutParams(
                LayoutParams.WRAP_CONTENT,
                LayoutParams.WRAP_CONTENT
        ));

        alternateStrip = new android.widget.LinearLayout(context);
        alternateStrip.setOrientation(android.widget.LinearLayout.HORIZONTAL);
        GradientDrawable stripBackground = new GradientDrawable();
        stripBackground.setColor(dark ? Color.rgb(66, 63, 74) : Color.rgb(255, 255, 255));
        stripBackground.setCornerRadius(dp(10));
        stripBackground.setStroke(
                Math.max(1, dp(1)),
                dark ? Color.rgb(96, 92, 106) : Color.rgb(203, 199, 214)
        );
        alternateStrip.setBackground(stripBackground);
        alternateStrip.setVisibility(GONE);
        addView(alternateStrip, new LayoutParams(
                LayoutParams.WRAP_CONTENT,
                LayoutParams.WRAP_CONTENT
        ));
    }

    public void setAlternateListener(AlternateListener listener) {
        alternateListener = listener;
    }

    /**
     * Shows the preview above the pressed key, clamped inside the overlay so an edge key
     * never renders partially off-screen.
     */
    public void show(KeySpec key, View keyView) {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(keyView, "keyView");
        if (!previewEligible(key)) {
            hide();
            return;
        }
        previewLabel.setText(key.label());
        scriptTypefaces.apply(previewLabel, key.label(), previewLabel.getTypeface());
        shownKeyId = key.keyId();
        setVisibility(VISIBLE);
        previewLabel.measure(
                MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED),
                MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED)
        );
        positionAbove(keyView);
    }

    /**
     * Shows the long-press variants for a key. Returns false when the key has none, so the
     * caller can fall back to its normal long-press handling.
     */
    public boolean showAlternates(KeySpec key, View keyView) {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(keyView, "keyView");
        if (!key.hasAlternates()) {
            return false;
        }
        shownKey = key;
        shownKeyId = key.keyId();
        shownAlternates = key.alternates();
        highlightedAlternate = 0;
        previewLabel.setVisibility(GONE);
        alternateStrip.removeAllViews();
        for (String alternate : shownAlternates) {
            TextView cell = new TextView(getContext());
            cell.setText(alternate);
            cell.setContentDescription(alternate);
            scriptTypefaces.apply(cell, alternate, cell.getTypeface());
            cell.setTextSize(TypedValue.COMPLEX_UNIT_SP, PREVIEW_TEXT_SIZE_SP);
            cell.setTextColor(darkTheme ? Color.rgb(244, 242, 248) : Color.rgb(34, 32, 38));
            cell.setGravity(Gravity.CENTER);
            cell.setMinWidth(dp(44));
            cell.setMinHeight(dp(48));
            cell.setPadding(dp(8), dp(6), dp(8), dp(6));
            alternateStrip.addView(cell);
        }
        applyAlternateHighlight();
        setVisibility(VISIBLE);
        alternateStrip.setVisibility(VISIBLE);
        alternateStrip.measure(
                MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED),
                MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED)
        );
        positionStripAbove(keyView);
        return true;
    }

    /** Tracks the finger across the open strip and highlights the variant under it. */
    public void moveAlternateSelection(float windowX) {
        if (!alternatesShowing()) {
            return;
        }
        int[] location = new int[2];
        alternateStrip.getLocationInWindow(location);
        float local = windowX - location[0];
        int index = -1;
        for (int position = 0; position < alternateStrip.getChildCount(); position++) {
            View cell = alternateStrip.getChildAt(position);
            if (local >= cell.getLeft() && local < cell.getRight()) {
                index = position;
                break;
            }
        }
        if (index >= 0 && index != highlightedAlternate) {
            highlightedAlternate = index;
            applyAlternateHighlight();
        }
    }

    /** Commits the highlighted variant. Returns true when a variant was chosen. */
    public boolean commitHighlightedAlternate() {
        if (!alternatesShowing()) {
            return false;
        }
        String chosen = shownAlternates.get(highlightedAlternate);
        KeySpec key = shownKey;
        hide();
        if (alternateListener != null && key != null) {
            alternateListener.onAlternateSelected(key, chosen);
            return true;
        }
        return false;
    }

    public boolean alternatesShowing() {
        return alternateStrip.getVisibility() == VISIBLE
                && highlightedAlternate >= 0
                && highlightedAlternate < shownAlternates.size();
    }

    String highlightedAlternateForTesting() {
        return alternatesShowing() ? shownAlternates.get(highlightedAlternate) : null;
    }

    int alternateCountForTesting() {
        return alternateStrip.getChildCount();
    }

    private void applyAlternateHighlight() {
        for (int position = 0; position < alternateStrip.getChildCount(); position++) {
            View cell = alternateStrip.getChildAt(position);
            boolean active = position == highlightedAlternate;
            cell.setActivated(active);
            cell.setBackgroundColor(active
                    ? (darkTheme ? Color.rgb(96, 92, 106) : Color.rgb(214, 210, 228))
                    : Color.TRANSPARENT);
        }
    }

    private void positionStripAbove(View keyView) {
        int[] overlayLocation = new int[2];
        int[] keyLocation = new int[2];
        getLocationInWindow(overlayLocation);
        keyView.getLocationInWindow(keyLocation);
        int width = alternateStrip.getMeasuredWidth();
        int height = alternateStrip.getMeasuredHeight();
        int centered = (keyLocation[0] - overlayLocation[0])
                + ((keyView.getWidth() - width) / 2);
        int maxLeft = Math.max(0, getWidth() - width);
        LayoutParams params = (LayoutParams) alternateStrip.getLayoutParams();
        params.leftMargin = Math.max(0, Math.min(centered, maxLeft));
        params.topMargin = Math.max(
                0,
                (keyLocation[1] - overlayLocation[1]) - height - previewOffsetPx
        );
        params.gravity = Gravity.TOP | Gravity.START;
        alternateStrip.setLayoutParams(params);
    }

    public void hide() {
        if (getVisibility() == GONE && shownKeyId == null) {
            return;
        }
        shownKeyId = null;
        shownKey = null;
        shownAlternates = java.util.Collections.emptyList();
        highlightedAlternate = -1;
        previewLabel.setText("");
        previewLabel.setVisibility(VISIBLE);
        alternateStrip.removeAllViews();
        alternateStrip.setVisibility(GONE);
        setVisibility(GONE);
    }

    public boolean isShowing() {
        return getVisibility() == VISIBLE && shownKeyId != null;
    }

    String shownKeyIdForTesting() {
        return shownKeyId;
    }

    /**
     * Action keys never preview. This matches the reference, where space, delete, enter,
     * shift, symbol, and language keys are deliberately silent.
     */
    static boolean previewEligible(KeySpec key) {
        return key.action() == KeySpec.Action.TEXT;
    }

    private void positionAbove(View keyView) {
        int[] overlayLocation = new int[2];
        int[] keyLocation = new int[2];
        getLocationInWindow(overlayLocation);
        keyView.getLocationInWindow(keyLocation);
        int keyLeft = keyLocation[0] - overlayLocation[0];
        int keyTop = keyLocation[1] - overlayLocation[1];

        int previewWidth = Math.max(previewLabel.getMeasuredWidth(), previewMinWidthPx);
        int previewHeight = previewLabel.getMeasuredHeight();
        int centeredLeft = keyLeft + ((keyView.getWidth() - previewWidth) / 2);
        int maxLeft = Math.max(0, getWidth() - previewWidth);
        int left = Math.max(0, Math.min(centeredLeft, maxLeft));
        int top = Math.max(0, keyTop - previewHeight - previewOffsetPx);

        LayoutParams params = (LayoutParams) previewLabel.getLayoutParams();
        params.leftMargin = left;
        params.topMargin = top;
        params.gravity = Gravity.TOP | Gravity.START;
        previewLabel.setLayoutParams(params);
    }

    private int dp(int value) {
        return Math.round(TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP,
                value,
                getResources().getDisplayMetrics()
        ));
    }
}
