#!/usr/bin/env bash
# Builds the Infinity Blade II and III Android ports with the squarer-screen fix:
#   src/out/ib2-android-<version>-squarer.apk   (com.ib2port.game)
#   src/out/ib3-android-<version>-squarer.apk   (com.ib3port.game)
#
# It clones the port (jelqedagain/ib-2-3-android, MIT) at the commit the fix was made and tested on,
# applies squarer-screens.patch, builds libib3.so with the NDK and packages both apps, the same way
# the port's own scripts/build-apk.sh does (that one expects Windows tools).
#
# Needs: git, the Android SDK with NDK 27.0.12077973, CMake 3.22.1, build-tools 36.0.0 and
# platforms/android-35 (sdkmanager "ndk;27.0.12077973" "cmake;3.22.1" "build-tools;36.0.0"
# "platforms;android-35"), a JDK 17+ (javac, keytool) and python3.
#   ANDROID_HOME   default ~/Library/Android/sdk
#   JAVA_HOME      default Android Studio's bundled JBR on macOS
#   IB_PORT_KEYSTORE  signing keystore (alias ib3, password ib3port); default src/out/ib-port-local.keystore,
#                     made on first use (kept out of git)
# Android installs an update only when it is signed with the same key as the installed app, so an APK
# from another key (the port's official release, the Releases page, a build from another machine)
# cannot be installed over it: see ../dist/INSTALL.md.
set -euo pipefail

UPSTREAM=https://github.com/jelqedagain/ib-2-3-android.git
COMMIT=9d707aa471a7c8b1eef9072958d11c24787e7349   # IB2 1.9.6 / IB3 1.9.5, 2026-10-17

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/out"
SRC="$OUT/ib-2-3-android"
SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
NDK="$SDK/ndk/27.0.12077973"
CMAKE_BIN="$SDK/cmake/3.22.1/bin"
BT="$SDK/build-tools/36.0.0"
JAR="$SDK/platforms/android-35/android.jar"
export JAVA_HOME="${JAVA_HOME:-/Applications/Android Studio.app/Contents/jbr/Contents/Home}"
export PATH="$JAVA_HOME/bin:$CMAKE_BIN:$PATH"
case "$(uname -s)" in
    Darwin) HOST=darwin-x86_64 ;;
    Linux) HOST=linux-x86_64 ;;
    *) echo "build.sh runs on macOS or Linux" >&2; exit 1 ;;
esac
for need in "$NDK" "$CMAKE_BIN/cmake" "$BT/aapt2" "$JAR" "$JAVA_HOME/bin/javac"; do
    [ -e "$need" ] || { echo "missing: $need" >&2; exit 1; }
done
mkdir -p "$OUT"

# 1. The port's source at the tested commit, with the fix.
if [ ! -d "$SRC/.git" ]; then
    git clone --quiet "$UPSTREAM" "$SRC"
fi
git -C "$SRC" checkout --quiet --force "$COMMIT"
git -C "$SRC" clean --quiet -fdx -e build-android
git -C "$SRC" apply "$HERE/squarer-screens.patch"
VERSION="$(sed -n 's/.*android:versionName="\([^"]*\)".*/\1/p' "$SRC/android/AndroidManifest.xml")"

# 2. libib3.so (the Android build needs no submodules or Boost; those are for the Windows runtime).
BUILD="$SRC/build-android"
if [ ! -f "$BUILD/build.ninja" ]; then
    cmake -S "$SRC" -B "$BUILD" -G Ninja -DCMAKE_MAKE_PROGRAM="$CMAKE_BIN/ninja" \
        -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
        -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-29 -DCMAKE_BUILD_TYPE=RelWithDebInfo >/dev/null
fi
cmake --build "$BUILD" --target ib3

# 3. The launcher (Java) and the shared parts of both APKs.
W="$OUT/work"
rm -rf "$W" && mkdir -p "$W/classes" "$W/lib/arm64-v8a" "$W/icon/drawable" "$W/icon/mipmap-anydpi-v26"
javac --release 11 -encoding UTF-8 -classpath "$JAR" -d "$W/classes" -Xlint:-options -nowarn \
    $(find "$SRC/android/java" -name '*.java')
java -cp "$BT/lib/d8.jar" com.android.tools.r8.D8 --release --min-api 29 --lib "$JAR" --output "$W" \
    $(find "$W/classes" -name '*.class')
"$NDK/toolchains/llvm/prebuilt/$HOST/bin/llvm-strip" -o "$W/lib/arm64-v8a/libib3.so" "$BUILD/libib3.so"
"$BT/aapt2" compile --dir "$SRC/android/res" -o "$W/res.zip"
# The official launcher icons are not in the port's repository: a plain one (the launcher can put
# the game's own icon from your .ipa on the home screen).
cat > "$W/icon/drawable/ic_bg.xml" <<'EOF'
<shape xmlns:android="http://schemas.android.com/apk/res/android"><solid android:color="#FF24508C"/></shape>
EOF
cat > "$W/icon/mipmap-anydpi-v26/ic_launcher.xml" <<'EOF'
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
  <background android:drawable="@drawable/ic_bg"/><foreground android:drawable="@drawable/ic_bg"/>
</adaptive-icon>
EOF
"$BT/aapt2" compile --dir "$W/icon" -o "$W/icon.zip"

KEYSTORE="${IB_PORT_KEYSTORE:-$OUT/ib-port-local.keystore}"
if [ ! -f "$KEYSTORE" ]; then
    keytool -genkeypair -keystore "$KEYSTORE" -storepass ib3port -keypass ib3port -alias ib3 \
        -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=IB Port local build" >/dev/null 2>&1
fi

# package <id> <label> <package> <.ipa bundle id> <.ipa version> <space needed>
package() {
    local P="$W/$1" APK="$OUT/$1-android-$VERSION-squarer.apk"
    mkdir -p "$P"
    sed -e "s|@LABEL@|$2|" -e "s|@PACKAGE@|$3|" -e "s|@BUNDLE_ID@|$4|" -e "s|@IPA_VERSION@|$5|" -e "s|@SIZE@|$6|" \
        "$SRC/android/AndroidManifest.xml" > "$P/AndroidManifest.xml"
    "$BT/aapt2" link -o "$P/unsigned.apk" -I "$JAR" --manifest "$P/AndroidManifest.xml" \
        --min-sdk-version 29 --target-sdk-version 35 "$W/res.zip" "$W/icon.zip"
    python3 - "$W" "$P/unsigned.apk" <<'EOF'
import sys, zipfile
work, apk = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(apk, "a", zipfile.ZIP_DEFLATED) as z:
    z.write(work + "/classes.dex", "classes.dex")
    z.write(work + "/lib/arm64-v8a/libib3.so", "lib/arm64-v8a/libib3.so")
EOF
    "$BT/zipalign" -f -p 4 "$P/unsigned.apk" "$P/aligned.apk"
    java -jar "$BT/lib/apksigner.jar" sign --ks "$KEYSTORE" --ks-pass pass:ib3port --key-pass pass:ib3port \
        --out "$APK" "$P/aligned.apk"
    echo "$APK"
}

package ib2 IB2 com.ib2port.game com.chairentertainment.IB2 1.3.5 "1.5 GB"
package ib3 IB3 com.ib3port.game com.chairentertainment.IB3 1.4.4 "3 GB"
rm -rf "$W"
