pluginManagement {
    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == "com.android.library" ||
                requested.id.id == "com.android.application"
            ) {
                useModule("com.android.tools.build:gradle:8.12.2")
            }
        }
    }
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "nepa-keyboard-android"
include(":pack-runtime")
include(":conversion-runtime")
include(":benchmark-app")
include(":ime-app")
