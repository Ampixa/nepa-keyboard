package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.os.Build;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;

/** Consistent edge-to-edge system-bar avoidance for the app's launcher activities. */
final class ActivitySystemBarInsets {
    private ActivitySystemBarInsets() {
    }

    static State install(Activity activity, View root) {
        return install(activity, root, false, null);
    }

    static State install(Activity activity, View root, boolean includeIme) {
        return install(activity, root, includeIme, null);
    }

    static State install(
            Activity activity,
            View root,
            boolean includeIme,
            Runnable afterInsetsApplied
    ) {
        Window window = activity.getWindow();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.setDecorFitsSystemWindows(false);
        } else {
            View decor = window.getDecorView();
            decor.setSystemUiVisibility(
                    decor.getSystemUiVisibility()
                            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            );
        }

        State state = new State(
                root.getPaddingLeft(),
                root.getPaddingTop(),
                root.getPaddingRight(),
                root.getPaddingBottom(),
                includeIme
        );
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            state.apply(view, insets);
            if (afterInsetsApplied != null) {
                view.post(afterInsetsApplied);
            }
            return insets;
        });
        root.requestApplyInsets();
        return state;
    }

    static final class State {
        private final int baseLeft;
        private final int baseTop;
        private final int baseRight;
        private final int baseBottom;
        private final boolean includeIme;
        private volatile int insetLeft;
        private volatile int insetTop;
        private volatile int insetRight;
        private volatile int insetBottom;
        private volatile boolean applied;

        State(
                int baseLeft,
                int baseTop,
                int baseRight,
                int baseBottom,
                boolean includeIme
        ) {
            this.baseLeft = baseLeft;
            this.baseTop = baseTop;
            this.baseRight = baseRight;
            this.baseBottom = baseBottom;
            this.includeIme = includeIme;
        }

        private void apply(View view, WindowInsets insets) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                android.graphics.Insets bars = insets.getInsets(
                        WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout()
                );
                insetLeft = bars.left;
                insetTop = bars.top;
                insetRight = bars.right;
                insetBottom = bars.bottom;
                if (includeIme) {
                    android.graphics.Insets ime = insets.getInsets(
                            WindowInsets.Type.ime()
                    );
                    insetBottom = Math.max(insetBottom, ime.bottom);
                }
            } else {
                // Stable insets exclude the transient IME height while retaining
                // status, navigation, and display-cutout avoidance.
                insetLeft = insets.getStableInsetLeft();
                insetTop = insets.getStableInsetTop();
                insetRight = insets.getStableInsetRight();
                insetBottom = insets.getStableInsetBottom();
                if (includeIme) {
                    insetBottom = Math.max(
                            insetBottom,
                            insets.getSystemWindowInsetBottom()
                    );
                }
            }
            view.setPadding(
                    baseLeft + insetLeft,
                    baseTop + insetTop,
                    baseRight + insetRight,
                    baseBottom + insetBottom
            );
            applied = true;
        }

        boolean matches(View view) {
            return applied
                    && view.getPaddingLeft() == baseLeft + insetLeft
                    && view.getPaddingTop() == baseTop + insetTop
                    && view.getPaddingRight() == baseRight + insetRight
                    && view.getPaddingBottom() == baseBottom + insetBottom;
        }
    }
}
