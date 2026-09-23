package com.ampixa.nepakeyboard.ime;

import android.annotation.SuppressLint;
import android.content.Context;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.GridView;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * Emoji panel shown in place of the key surface.
 *
 * <p>Every cell is a real focusable control with its own accessible label, so the grid is
 * navigable rather than a single opaque canvas.
 */
@SuppressLint("ViewConstructor")
public final class EmojiPanel extends LinearLayout {
    public interface Listener {
        void onEmojiSelected(String emoji);

        void onEmojiBackspace();

        void onEmojiDismissed();
    }

    static final String RECENTS_CATEGORY_ID = "recents";
    private static final int COLUMN_WIDTH_DP = 60;
    private static final int EMOJI_TEXT_SIZE_SP = 28;
    private static final int TAB_HEIGHT_DP = 48;
    private static final int ACTION_BAR_HEIGHT_DP = 48;

    private final Listener listener;
    private int textColor;
    private int accentColor;
    private final LinearLayout tabStrip;
    private final GridView grid;
    private final EmojiAdapter adapter;
    private final TextView backButton;
    private final TextView backspaceButton;
    private final List<Page> pages = new ArrayList<>();
    private int activePage;

    public EmojiPanel(Context context, Listener listener) {
        super(context);
        this.listener = Objects.requireNonNull(listener, "listener");
        boolean dark = (context.getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        textColor = dark ? Color.rgb(244, 242, 248) : Color.rgb(34, 32, 38);
        accentColor = dark ? Color.rgb(166, 158, 255) : Color.rgb(84, 63, 208);
        setOrientation(VERTICAL);
        setBackgroundColor(dark ? Color.rgb(30, 29, 34) : Color.rgb(240, 238, 244));

        HorizontalScrollView tabScroller = new HorizontalScrollView(context);
        tabScroller.setFillViewport(true);
        tabScroller.setHorizontalScrollBarEnabled(false);
        tabStrip = new LinearLayout(context);
        tabStrip.setOrientation(HORIZONTAL);
        tabScroller.addView(tabStrip, new LayoutParams(
                LayoutParams.WRAP_CONTENT,
                LayoutParams.MATCH_PARENT
        ));
        addView(tabScroller, new LayoutParams(LayoutParams.MATCH_PARENT, dp(TAB_HEIGHT_DP)));

        grid = new GridView(context);
        grid.setNumColumns(GridView.AUTO_FIT);
        grid.setColumnWidth(dp(COLUMN_WIDTH_DP));
        grid.setStretchMode(GridView.STRETCH_COLUMN_WIDTH);
        grid.setVerticalScrollBarEnabled(true);
        adapter = new EmojiAdapter();
        grid.setAdapter(adapter);
        addView(grid, new LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f));

        LinearLayout actions = new LinearLayout(context);
        actions.setOrientation(HORIZONTAL);
        actions.setGravity(Gravity.CENTER_VERTICAL);
        backButton = actionButton(
                getContext().getString(R.string.emoji_back_to_keys),
                getContext().getString(R.string.emoji_back_to_keys)
        );
        backButton.setOnClickListener(view -> listener.onEmojiDismissed());
        actions.addView(backButton, new LayoutParams(0, dp(ACTION_BAR_HEIGHT_DP), 1f));
        backspaceButton = actionButton(
                "⌫",
                getContext().getString(R.string.delete_key)
        );
        backspaceButton.setOnClickListener(view -> listener.onEmojiBackspace());
        actions.addView(backspaceButton, new LayoutParams(0, dp(ACTION_BAR_HEIGHT_DP), 1f));
        addView(actions, new LayoutParams(LayoutParams.MATCH_PARENT, dp(ACTION_BAR_HEIGHT_DP)));
    }

    /** Keeps the emoji surface visually continuous with the selected keyboard theme. */
    public void setTheme(KeyboardTheme theme) {
        Objects.requireNonNull(theme, "theme");
        textColor = theme.secondaryTextColor();
        accentColor = theme.textColor();
        setBackgroundColor(theme.surfaceColor());
        backButton.setTextColor(theme.textColor());
        backspaceButton.setTextColor(theme.textColor());
        renderTabs();
    }

    /** Binds the bundled catalog plus the current recents page. */
    public void bind(EmojiCatalog catalog, List<String> recents) {
        Objects.requireNonNull(catalog, "catalog");
        Objects.requireNonNull(recents, "recents");
        pages.clear();
        pages.add(new Page(RECENTS_CATEGORY_ID, new ArrayList<>(recents)));
        for (EmojiCatalog.Category category : catalog.categories()) {
            pages.add(new Page(category.id(), category.emoji()));
        }
        // A first run has no recents; opening on an empty grid looks broken.
        activePage = recents.isEmpty() && pages.size() > 1 ? 1 : 0;
        renderTabs();
        renderGrid();
    }

    /** Refreshes the recents page in place after a selection. */
    public void updateRecents(List<String> recents) {
        if (pages.isEmpty()) {
            return;
        }
        pages.set(0, new Page(RECENTS_CATEGORY_ID, new ArrayList<>(recents)));
        if (activePage == 0) {
            renderGrid();
        }
    }

    int activePageForTesting() {
        return activePage;
    }

    String activeCategoryForTesting() {
        return pages.isEmpty() ? null : pages.get(activePage).id;
    }

    int visibleEmojiCountForTesting() {
        return adapter.getCount();
    }

    int pageCountForTesting() {
        return pages.size();
    }

    boolean themeMatchesForTesting(KeyboardTheme theme) {
        if (!(getBackground() instanceof ColorDrawable)
                || ((ColorDrawable) getBackground()).getColor() != theme.surfaceColor()
                || backButton.getCurrentTextColor() != theme.textColor()
                || backspaceButton.getCurrentTextColor() != theme.textColor()) {
            return false;
        }
        for (int index = 0; index < tabStrip.getChildCount(); index++) {
            View child = tabStrip.getChildAt(index);
            if (!(child instanceof TextView)) {
                return false;
            }
            int expected = index == activePage
                    ? theme.textColor()
                    : theme.secondaryTextColor();
            if (((TextView) child).getCurrentTextColor() != expected) {
                return false;
            }
        }
        return true;
    }

    boolean selectPageForTesting(String categoryId) {
        for (int index = 0; index < pages.size(); index++) {
            if (pages.get(index).id.equals(categoryId)) {
                selectPage(index);
                return true;
            }
        }
        return false;
    }

    boolean selectEmojiForTesting(int position) {
        if (position < 0 || position >= adapter.getCount()) {
            return false;
        }
        listener.onEmojiSelected(adapter.getItem(position));
        return true;
    }

    boolean performBackspaceForTesting() {
        return backspaceButton.performClick();
    }

    boolean touchTargetsMeetMinimumForTesting() {
        int minimum = dp(48);
        if (backButton.getWidth() < minimum
                || backButton.getHeight() < minimum
                || backspaceButton.getWidth() < minimum
                || backspaceButton.getHeight() < minimum) {
            return false;
        }
        for (int index = 0; index < tabStrip.getChildCount(); index++) {
            View tab = tabStrip.getChildAt(index);
            if (tab.getWidth() < minimum || tab.getHeight() < minimum) {
                return false;
            }
        }
        return true;
    }

    private void selectPage(int index) {
        if (index < 0 || index >= pages.size() || index == activePage) {
            return;
        }
        activePage = index;
        renderTabs();
        renderGrid();
    }

    private void renderTabs() {
        tabStrip.removeAllViews();
        for (int index = 0; index < pages.size(); index++) {
            Page page = pages.get(index);
            boolean active = index == activePage;
            String label = categoryLabel(page.id);
            TextView tab = actionButton(label, label);
            tab.setTextColor(active ? accentColor : textColor);
            tab.setActivated(active);
            tab.setSelected(active);
            final int target = index;
            tab.setOnClickListener(view -> selectPage(target));
            LayoutParams params = new LayoutParams(
                    LayoutParams.WRAP_CONTENT,
                    LayoutParams.MATCH_PARENT
            );
            tabStrip.addView(tab, params);
        }
    }

    private void renderGrid() {
        adapter.setValues(pages.isEmpty()
                ? Collections.emptyList()
                : pages.get(activePage).emoji);
        grid.setSelection(0);
    }

    private String categoryLabel(String categoryId) {
        switch (categoryId) {
            case RECENTS_CATEGORY_ID:
                return getContext().getString(R.string.emoji_category_recents);
            case "smileys-people":
                return getContext().getString(R.string.emoji_category_smileys);
            case "animals-nature":
                return getContext().getString(R.string.emoji_category_animals);
            case "food-drink":
                return getContext().getString(R.string.emoji_category_food);
            case "activities":
                return getContext().getString(R.string.emoji_category_activities);
            case "travel-places":
                return getContext().getString(R.string.emoji_category_travel);
            case "objects":
                return getContext().getString(R.string.emoji_category_objects);
            case "symbols":
                return getContext().getString(R.string.emoji_category_symbols);
            case "flags":
                return getContext().getString(R.string.emoji_category_flags);
            default:
                throw new IllegalStateException("unknown emoji category: " + categoryId);
        }
    }

    private TextView actionButton(String label, String description) {
        TextView view = new TextView(getContext());
        view.setText(label);
        view.setContentDescription(description);
        view.setTextColor(textColor);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        view.setGravity(Gravity.CENTER);
        view.setPadding(dp(14), 0, dp(14), 0);
        view.setMinimumHeight(dp(48));
        view.setClickable(true);
        view.setFocusable(true);
        return view;
    }

    private int dp(int value) {
        return Math.round(TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP,
                value,
                getResources().getDisplayMetrics()
        ));
    }

    private static final class Page {
        private final String id;
        private final List<String> emoji;

        Page(String id, List<String> emoji) {
            this.id = id;
            this.emoji = emoji;
        }
    }

    private final class EmojiAdapter extends BaseAdapter {
        private List<String> values = Collections.emptyList();

        void setValues(List<String> next) {
            values = next;
            notifyDataSetChanged();
        }

        @Override
        public int getCount() {
            return values.size();
        }

        @Override
        public String getItem(int position) {
            return values.get(position);
        }

        @Override
        public long getItemId(int position) {
            return position;
        }

        @Override
        public View getView(int position, View convertView, ViewGroup parent) {
            TextView cell = convertView instanceof TextView
                    ? (TextView) convertView
                    : newCell();
            String value = getItem(position);
            cell.setText(value);
            cell.setContentDescription(value);
            cell.setOnClickListener(view -> listener.onEmojiSelected(value));
            return cell;
        }

        private TextView newCell() {
            TextView cell = new TextView(getContext());
            cell.setTextSize(TypedValue.COMPLEX_UNIT_SP, EMOJI_TEXT_SIZE_SP);
            cell.setGravity(Gravity.CENTER);
            cell.setHeight(dp(COLUMN_WIDTH_DP));
            cell.setClickable(true);
            cell.setFocusable(true);
            return cell;
        }
    }
}
