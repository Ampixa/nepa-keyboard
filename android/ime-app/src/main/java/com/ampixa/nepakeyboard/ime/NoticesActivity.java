package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import com.ampixa.nepakeyboard.pack.NkpBundle;

import java.io.File;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Verified, virtualized provenance notices for the active variant's installed packs. */
public final class NoticesActivity extends Activity {
    private final ExecutorService loader = Executors.newSingleThreadExecutor(runnable -> {
        Thread thread = new Thread(runnable, "nepa-notice-loader");
        thread.setDaemon(true);
        thread.setPriority(Thread.MIN_PRIORITY);
        return thread;
    });
    private final List<NoticeRow> rows = new ArrayList<>();
    private NoticeAdapter adapter;
    private TextView status;
    private ListView list;
    private LinearLayout root;
    private ActivitySystemBarInsets.State systemBarInsets;
    private int surfaceColor;
    private int textColor;
    private int secondaryTextColor;
    private int accentColor;
    private volatile boolean ready;
    private volatile int loadedSourceCount;
    private volatile int loadedLayoutNoticeCount;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        boolean dark = (getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        surfaceColor = dark ? Color.rgb(23, 22, 27) : Color.rgb(246, 245, 250);
        textColor = dark ? Color.rgb(246, 243, 248) : Color.rgb(31, 29, 35);
        secondaryTextColor = dark ? Color.rgb(199, 194, 204) : Color.rgb(92, 88, 99);
        accentColor = dark ? Color.rgb(197, 192, 255) : Color.rgb(79, 70, 165);
        render();
        loader.execute(this::loadNotices);
    }

    @Override
    protected void onDestroy() {
        loader.shutdownNow();
        super.onDestroy();
    }

    private void render() {
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(20), dp(20), dp(12));
        root.setBackgroundColor(surfaceColor);

        Button back = new Button(this);
        back.setAllCaps(false);
        back.setText(R.string.back);
        back.setTextColor(accentColor);
        back.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        back.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        back.setMinHeight(dp(48));
        back.setBackgroundColor(Color.TRANSPARENT);
        back.setContentDescription(getString(R.string.back));
        back.setOnClickListener(view -> finish());
        root.addView(back, fullWidth(ViewGroup.LayoutParams.WRAP_CONTENT));

        root.addView(text(getString(R.string.dictionary_notices_title), 28, textColor),
                fullWidth(ViewGroup.LayoutParams.WRAP_CONTENT));
        TextView summary = text(
                getString(R.string.dictionary_notices_summary),
                15,
                secondaryTextColor
        );
        LinearLayout.LayoutParams summaryParams = fullWidth(ViewGroup.LayoutParams.WRAP_CONTENT);
        summaryParams.setMargins(0, dp(6), 0, dp(12));
        root.addView(summary, summaryParams);

        status = text(getString(R.string.loading_notices), 16, secondaryTextColor);
        status.setGravity(Gravity.CENTER);
        status.setMinHeight(dp(96));
        root.addView(status, fullWidth(ViewGroup.LayoutParams.WRAP_CONTENT));

        adapter = new NoticeAdapter();
        list = new ListView(this);
        list.setDivider(null);
        list.setDividerHeight(0);
        list.setClipToPadding(false);
        list.setPadding(0, 0, 0, dp(16));
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> showDetail(rows.get(position)));
        LinearLayout.LayoutParams listParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f
        );
        root.addView(list, listParams);
        setContentView(root);
        systemBarInsets = ActivitySystemBarInsets.install(this, root);
    }

    private void loadNotices() {
        List<NoticeRow> loaded = new ArrayList<>();
        Set<String> seenArtifacts = new HashSet<>();
        boolean failed = false;
        for (ReleasePackSpec spec : ReleasePackRegistry.installed(getApplicationContext())) {
            String artifactKey = spec.packId() + ":" + spec.artifactSha256();
            if (!seenArtifacts.add(artifactKey)) {
                continue;
            }
            try {
                File materialized = spec.materialize();
                NkpBundle.NoticeDocument document = NoticeReaderFactory.read(
                        materialized,
                        spec.artifactSha256()
                );
                if (!spec.packId().equals(document.packId())) {
                    throw new SecurityException("pack notice ID mismatch");
                }
                for (NkpBundle.NoticeSource source : document.sources()) {
                    loaded.add(NoticeRow.dictionary(
                            document.packId(),
                            document.artifactLicense(),
                            source
                    ));
                }
            } catch (Exception invalidPack) {
                failed = true;
            }
        }
        try {
            for (LayoutNotices.Entry entry : LayoutNotices.read(getAssets())) {
                loaded.add(NoticeRow.layout(entry));
            }
        } catch (Exception invalidLayoutNotice) {
            failed = true;
        }
        loaded.sort(Comparator
                .comparing((NoticeRow row) -> row.itemId)
                .thenComparing(row -> row.title));
        boolean hadFailure = failed;
        runOnUiThread(() -> applyLoadedRows(loaded, hadFailure));
    }

    private void applyLoadedRows(List<NoticeRow> loaded, boolean failed) {
        if (isFinishing() || isDestroyed()) {
            return;
        }
        rows.clear();
        rows.addAll(loaded);
        int dictionaryCount = 0;
        int layoutCount = 0;
        for (NoticeRow row : rows) {
            if (row.layout) {
                layoutCount++;
            } else {
                dictionaryCount++;
            }
        }
        loadedSourceCount = dictionaryCount;
        loadedLayoutNoticeCount = layoutCount;
        ready = true;
        adapter.notifyDataSetChanged();
        if (rows.isEmpty()) {
            status.setText(failed
                    ? R.string.notices_unavailable
                    : R.string.no_dictionary_notices);
            status.setVisibility(View.VISIBLE);
        } else if (failed) {
            status.setText(R.string.some_notices_unavailable);
            status.setVisibility(View.VISIBLE);
        } else {
            status.setVisibility(View.GONE);
        }
    }

    private void showDetail(NoticeRow row) {
        StringBuilder message = new StringBuilder();
        message.append(row.layout ? getString(R.string.layout_label) : getString(R.string.pack_label))
                .append(": ").append(row.itemId);
        if (row.layout) {
            message.append("\n").append(getString(R.string.license_label))
                    .append(": ").append(row.sourceLicense);
            message.append("\n").append(getString(R.string.copyright_label))
                    .append(": ").append(row.changes);
        } else {
            message.append("\n").append(getString(R.string.artifact_license_label))
                    .append(": ").append(row.artifactLicense);
            message.append("\n").append(getString(R.string.source_license_label))
                    .append(": ").append(row.sourceLicense);
        }
        if (!row.licenseNotice.isEmpty()) {
            message.append("\n\n").append(row.licenseNotice);
        }
        if (!row.layout && !row.changes.isEmpty()) {
            message.append("\n\n").append(getString(R.string.changes_label))
                    .append(": ").append(row.changes);
        }
        if (row.sourceUrl != null) {
            message.append("\n\n").append(row.sourceUrl);
        }
        if (row.licenseUrl != null) {
            message.append("\n").append(row.licenseUrl);
        }

        AlertDialog.Builder dialog = new AlertDialog.Builder(this)
                .setTitle(row.title)
                .setMessage(message.toString());
        if (row.sourceUrl != null) {
            dialog.setPositiveButton(R.string.open_source, (ignored, which) ->
                    openExternal(row.sourceUrl));
        }
        if (row.licenseUrl != null) {
            dialog.setNeutralButton(R.string.open_license, (ignored, which) ->
                    openExternal(row.licenseUrl));
        }
        dialog.setNegativeButton(R.string.close, null).show();
    }

    private void openExternal(String rawUrl) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(rawUrl)));
        } catch (ActivityNotFoundException unavailable) {
            Toast.makeText(this, R.string.no_browser_available, Toast.LENGTH_SHORT).show();
        }
    }

    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextColor(color);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, size);
        return view;
    }

    private LinearLayout.LayoutParams fullWidth(int height) {
        return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, height);
    }

    private int dp(int value) {
        return Math.round(TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP,
                value,
                getResources().getDisplayMetrics()
        ));
    }

    boolean noticesReadyForTesting() {
        return ready;
    }

    int visibleNoticeSourcesForTesting() {
        return loadedSourceCount;
    }

    int visibleLayoutNoticesForTesting() {
        return loadedLayoutNoticeCount;
    }

    boolean noticeListIsVirtualizedForTesting() {
        return list != null && list.getAdapter() == adapter;
    }

    boolean systemBarInsetsAppliedForTesting() {
        return root != null
                && systemBarInsets != null
                && systemBarInsets.matches(root);
    }

    private final class NoticeAdapter extends BaseAdapter {
        @Override
        public int getCount() {
            return rows.size();
        }

        @Override
        public Object getItem(int position) {
            return rows.get(position);
        }

        @Override
        public long getItemId(int position) {
            return position;
        }

        @Override
        public View getView(int position, View convertView, ViewGroup parent) {
            NoticeRow row = rows.get(position);
            LinearLayout container;
            NoticeViewHolder holder;
            if (convertView instanceof LinearLayout
                    && convertView.getTag() instanceof NoticeViewHolder) {
                container = (LinearLayout) convertView;
                holder = (NoticeViewHolder) convertView.getTag();
            } else {
                container = new LinearLayout(NoticesActivity.this);
                container.setOrientation(LinearLayout.VERTICAL);
                container.setPadding(dp(16), dp(12), dp(16), dp(12));
                container.setMinimumHeight(dp(64));
                TextView title = text("", 17, textColor);
                TextView subtitle = text("", 14, secondaryTextColor);
                container.addView(title);
                container.addView(subtitle);
                holder = new NoticeViewHolder(title, subtitle);
                container.setTag(holder);
            }
            container.setContentDescription(
                    row.title + ", " + row.sourceLicense
            );
            holder.title.setText(row.title);
            holder.subtitle.setText(getString(
                    R.string.notice_row_summary,
                    row.itemId,
                    row.sourceLicense
            ));
            return container;
        }
    }

    private static final class NoticeViewHolder {
        final TextView title;
        final TextView subtitle;

        NoticeViewHolder(TextView title, TextView subtitle) {
            this.title = title;
            this.subtitle = subtitle;
        }
    }

    private static final class NoticeRow {
        final String itemId;
        final String title;
        final String artifactLicense;
        final String sourceLicense;
        final String licenseNotice;
        final String changes;
        final String sourceUrl;
        final String licenseUrl;
        final boolean layout;

        private NoticeRow(
                String itemId,
                String title,
                String artifactLicense,
                String sourceLicense,
                String licenseNotice,
                String changes,
                String sourceUrl,
                String licenseUrl,
                boolean layout
        ) {
            this.itemId = itemId;
            this.title = title;
            this.artifactLicense = artifactLicense;
            this.sourceLicense = sourceLicense;
            this.licenseNotice = licenseNotice;
            this.changes = changes;
            this.sourceUrl = sourceUrl;
            this.licenseUrl = licenseUrl;
            this.layout = layout;
        }

        static NoticeRow dictionary(
                String packId,
                String artifactLicense,
                NkpBundle.NoticeSource source
        ) {
            return new NoticeRow(
                    packId,
                    source.title(),
                    artifactLicense,
                    source.license(),
                    source.licenseNotice(),
                    source.changes(),
                    source.sourceUrl(),
                    source.licenseUrl(),
                    false
            );
        }

        static NoticeRow layout(LayoutNotices.Entry entry) {
            return new NoticeRow(
                    entry.layoutId(),
                    entry.displayName(),
                    entry.licenseId(),
                    entry.licenseId(),
                    entry.notice(),
                    entry.copyright(),
                    entry.sourceUrl(),
                    entry.licenseUrl(),
                    true
            );
        }
    }
}
