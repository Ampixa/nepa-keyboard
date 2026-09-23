package com.ampixa.nepakeyboard.ime;

import android.content.Context;
import android.os.Build;
import android.os.IBinder;
import android.inputmethodservice.InputMethodService;
import android.view.inputmethod.InputMethodInfo;
import android.view.inputmethod.InputMethodManager;
import android.view.inputmethod.InputMethodSubtype;

import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Exact runtime bridge between generated profile IDs and Android IME subtypes. */
final class AndroidSubtypeRegistry {
    private static final String PROFILE_EXTRA = "profile";

    enum SwitchPath {
        INPUT_METHOD_SERVICE("input_method_service"),
        LEGACY_IME_WINDOW_TOKEN("legacy_ime_window_token");

        final String resultName;

        SwitchPath(String resultName) {
            this.resultName = resultName;
        }
    }

    static final class SwitchOutcome {
        final SwitchPath path;
        final boolean legacyWindowTokenPresent;
        final boolean dispatched;

        SwitchOutcome(
                SwitchPath path,
                boolean legacyWindowTokenPresent,
                boolean dispatched
        ) {
            this.path = Objects.requireNonNull(path, "path");
            this.legacyWindowTokenPresent = legacyWindowTokenPresent;
            this.dispatched = dispatched;
        }
    }

    private final InputMethodManager inputMethodManager;
    private final InputMethodInfo inputMethodInfo;
    private final Map<String, InputMethodSubtype> byProfileId;

    static AndroidSubtypeRegistry load(Context context) {
        Objects.requireNonNull(context, "context");
        InputMethodManager manager = context.getSystemService(InputMethodManager.class);
        if (manager == null) {
            throw new IllegalStateException("Android input-method manager is unavailable");
        }
        String packageName = context.getPackageName();
        String serviceName = NepaInputMethodService.class.getName();
        InputMethodInfo ownInputMethod = null;
        for (InputMethodInfo candidate : manager.getInputMethodList()) {
            if (packageName.equals(candidate.getPackageName())
                    && serviceName.equals(candidate.getServiceName())) {
                if (ownInputMethod != null) {
                    throw new IllegalStateException("duplicate installed Nepa input method");
                }
                ownInputMethod = candidate;
            }
        }
        if (ownInputMethod == null) {
            throw new IllegalStateException("installed Nepa input method metadata is unavailable");
        }
        return new AndroidSubtypeRegistry(manager, ownInputMethod);
    }

    private AndroidSubtypeRegistry(
            InputMethodManager inputMethodManager,
            InputMethodInfo inputMethodInfo
    ) {
        this.inputMethodManager = inputMethodManager;
        this.inputMethodInfo = inputMethodInfo;
        Map<String, InputMethodSubtype> subtypes = new LinkedHashMap<>();
        Set<Integer> subtypeIds = new HashSet<>();
        for (int index = 0; index < inputMethodInfo.getSubtypeCount(); index++) {
            InputMethodSubtype subtype = inputMethodInfo.getSubtypeAt(index);
            String profileId = subtype.getExtraValueOf(PROFILE_EXTRA);
            KeyboardProfile profile = LanguageRegistry.find(profileId);
            if (profile == null
                    || !profile.isAvailable()
                    || !"keyboard".equals(subtype.getMode())
                    || !profile.localeTag().equalsIgnoreCase(subtype.getLanguageTag())) {
                throw new IllegalStateException(
                        "installed Nepa subtype does not match an available profile"
                );
            }
            if (subtype.hashCode() <= 0 || !subtypeIds.add(subtype.hashCode())) {
                throw new IllegalStateException("installed Nepa subtype ID is invalid or duplicate");
            }
            if (subtypes.put(profileId, subtype) != null) {
                throw new IllegalStateException("duplicate installed subtype profile: " + profileId);
            }
        }
        if (subtypes.size() != LanguageRegistry.subtypeBacked().size()) {
            throw new IllegalStateException("installed Nepa subtype count does not match catalog");
        }
        for (KeyboardProfile profile : LanguageRegistry.subtypeBacked()) {
            if (!subtypes.containsKey(profile.id())) {
                throw new IllegalStateException(
                        "installed Nepa subtype is missing profile: " + profile.id()
                );
            }
        }
        byProfileId = java.util.Collections.unmodifiableMap(subtypes);
    }

    String inputMethodId() {
        return inputMethodInfo.getId();
    }

    InputMethodInfo inputMethodInfoForTesting() {
        return inputMethodInfo;
    }

    InputMethodSubtype subtypeForProfile(String profileId) {
        return profileId == null ? null : byProfileId.get(profileId);
    }

    KeyboardProfile profileForSubtype(InputMethodSubtype subtype) {
        if (subtype == null) {
            return null;
        }
        String profileId = subtype.getExtraValueOf(PROFILE_EXTRA);
        InputMethodSubtype declared = byProfileId.get(profileId);
        if (declared == null || !declared.equals(subtype)) {
            return null;
        }
        KeyboardProfile profile = LanguageRegistry.find(profileId);
        if (profile == null
                || !profile.isAvailable()
                || !"keyboard".equals(subtype.getMode())
                || !profile.localeTag().equalsIgnoreCase(subtype.getLanguageTag())) {
            return null;
        }
        return profile;
    }

    InputMethodSubtype currentSubtype() {
        return inputMethodManager.getCurrentInputMethodSubtype();
    }

    KeyboardProfile currentProfile() {
        return profileForSubtype(currentSubtype());
    }

    /**
     * Requests the exact generated subtype on every supported API level.
     *
     * <p>The API 26-27 branch requires the identifying token attached to the active IME.
     * Callers must wait until that token exists; a null token is rejected without mutation.</p>
     */
    @SuppressWarnings("deprecation")
    SwitchOutcome requestSwitch(
            InputMethodService service,
            IBinder legacyImeToken,
            String profileId
    ) {
        Objects.requireNonNull(service, "service");
        InputMethodSubtype subtype = subtypeForProfile(profileId);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            if (subtype == null) {
                return new SwitchOutcome(
                        SwitchPath.INPUT_METHOD_SERVICE,
                        legacyImeToken != null,
                        false
                );
            }
            try {
                service.switchInputMethod(inputMethodInfo.getId(), subtype);
                return new SwitchOutcome(
                        SwitchPath.INPUT_METHOD_SERVICE,
                        legacyImeToken != null,
                        true
                );
            } catch (RuntimeException platformSwitchFailure) {
                return new SwitchOutcome(
                        SwitchPath.INPUT_METHOD_SERVICE,
                        legacyImeToken != null,
                        false
                );
            }
        }
        if (subtype == null || legacyImeToken == null) {
            return new SwitchOutcome(
                    SwitchPath.LEGACY_IME_WINDOW_TOKEN,
                    legacyImeToken != null,
                    false
            );
        }
        try {
            inputMethodManager.setInputMethodAndSubtype(
                    legacyImeToken,
                    inputMethodInfo.getId(),
                    subtype
            );
            return new SwitchOutcome(
                    SwitchPath.LEGACY_IME_WINDOW_TOKEN,
                    true,
                    true
            );
        } catch (RuntimeException platformSwitchFailure) {
            return new SwitchOutcome(
                    SwitchPath.LEGACY_IME_WINDOW_TOKEN,
                    true,
                    false
            );
        }
    }

    /** Mirrors Nepa's enabled set into Android where the managed API exists. */
    boolean synchronizeEnabledProfiles(List<KeyboardProfile> enabledProfiles) {
        Objects.requireNonNull(enabledProfiles, "enabledProfiles");
        if (enabledProfiles.isEmpty()) {
            throw new IllegalArgumentException("at least one subtype must remain enabled");
        }
        int[] subtypeIds = new int[enabledProfiles.size()];
        for (int index = 0; index < enabledProfiles.size(); index++) {
            KeyboardProfile profile = enabledProfiles.get(index);
            InputMethodSubtype subtype = subtypeForProfile(profile.id());
            if (subtype == null) {
                throw new IllegalArgumentException(
                        "enabled profile has no generated subtype: " + profile.id()
                );
            }
            subtypeIds[index] = subtype.hashCode();
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            return false;
        }
        inputMethodManager.setExplicitlyEnabledInputMethodSubtypes(
                inputMethodInfo.getId(),
                subtypeIds
        );
        return true;
    }
}
