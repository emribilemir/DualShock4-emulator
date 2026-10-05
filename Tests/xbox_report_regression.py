"""Extract actual Xbox/report blocks and compare against the existing trigger-fix commit.

Generates C++ to compile with MSVC. No replacement implementation of input mapping.
"""
import argparse
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = "10d934e10d16ec892e82263cc0103f94a7bea7de"


def between(text, start, end):
    a = text.index(start)
    return text[a:text.index(end, a)]


def mapper(source, name):
    mapping = between(source, "// Convert axis from", "\n\t\t\t}\n\t\t}\n\t\t// Mouse and keyboard mode")
    start = "if (!XboxStickTouchActive)" if "if (!XboxStickTouchActive)" in source else "Touch1.IsChanged ="
    packing = between(source, start, "// freePIE gyro")
    motion_start = source.rindex("// Motion shaking")
    motion = source[motion_start:source.index("// Special keys", motion_start)]
    setup = """
Result NAME(XINPUT_STATE myPState, const Config& c, State& state) {
    DS4_REPORT_EX report; DS4_REPORT_INIT_EX(&report);
    auto& Touch1 = state.t1; auto& Touch2 = state.t2;
    Touch1.X = Touch1.Y = Touch2.X = Touch2.Y = 0;
    auto& LastTouch = state.last; auto& LastTouchValid = state.valid;
    auto& TouchPacket = state.packet;
    report.sCurrentTouch.bIsUpTrackingNum1 = uint8_t(0x80 | Touch1.ID);
    report.sCurrentTouch.bIsUpTrackingNum2 = uint8_t(0x80 | Touch2.ID);
    bool InvertX = c.ix, InvertY = c.iy, EnableXboxButton = true;
    bool SwapTriggersShoulders = c.swap, DisableButtonOnMotion = c.disable;
    bool SwapShareTouchPad = c.share, TouchPadPressedWhenSwiping = c.click;
    int KEY_ID_XBOX_ACTIVATE_MULTI = XINPUT_GAMEPAD_BACK;
    int KEY_ID_XBOX_MOTION_SHAKING = XINPUT_GAMEPAD_RIGHT_SHOULDER;
    int KEY_ID_XBOX_MOTION_X_ADD = XINPUT_GAMEPAD_DPAD_UP, KEY_ID_XBOX_MOTION_X_SUB = XINPUT_GAMEPAD_DPAD_DOWN;
    int KEY_ID_XBOX_MOTION_Y_ADD = 0, KEY_ID_XBOX_MOTION_Y_SUB = 0;
    int KEY_ID_XBOX_MOTION_Z_ADD = XINPUT_GAMEPAD_DPAD_LEFT, KEY_ID_XBOX_MOTION_Z_SUB = XINPUT_GAMEPAD_DPAD_RIGHT;
    bool MotionShaking = false, MotionXAdd = false, MotionXSub = false, MotionYAdd = false;
    bool MotionYSub = false, MotionZAdd = false, MotionZSub = false, MotionShakingSwap = false;
    auto& TouchpadStickState = state.stick;
    const auto& TouchpadStickSettings = c.touch;
    const double TouchpadStickDelta = 0.01;
    bool XboxStickTouchActive = false;
    bool XboxStickMotionActive = false;
    XboxMotion::Rate XboxStickMotionRate;
    bool MotionStickEnabled = c.motionEnabled;
    int MotionStickKey = c.motionKey;
    const auto& MotionStickSettings = c.motion;
""".replace("NAME", name)
    return setup + mapping + packing + motion + """
    unsigned motions = MotionShaking | (MotionXAdd << 1) | (MotionXSub << 2) | (MotionYAdd << 3)
        | (MotionYSub << 4) | (MotionZAdd << 5) | (MotionZSub << 6);
    return {report, motions, XboxActivateMotionPressed};
}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    old = subprocess.check_output(["git", "show", BASELINE + ":Source/DS4Emulator.cpp"], cwd=ROOT).decode("utf-8-sig").replace("\r\n", "\n")
    new = (ROOT / "Source/DS4Emulator.cpp").read_text(encoding="utf-8-sig")
    trigger_start = "// Allow triggers while"
    assert between(old, trigger_start, "// Touchpad swipes") == between(new, trigger_start, "// Touchpad swipes"), "Trigger fix was modified"
    suppression = "if (XboxActivateMotionPressed) {\n\t\t\t\t\treport.bThumbLX = 128; report.bThumbLY = 128;\n\t\t\t\t\treport.bThumbRX = 128; report.bThumbRY = 128;\n\t\t\t\t}"
    assert suppression in new
    header = (ROOT / "Source/DS4Emulator.h").read_text(encoding="cp1251")
    preamble = """
#include <Windows.h>
#include <cmath>
#include <cstdint>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "../../Source/ViGEm/Common.h"
#include "../../Source/XboxTouchpad.h"
#include "../../Source/XboxMotion.h"
bool IsKeyPressed(int) { return false; }
const int KEY_ID_SHARE = 0;
"""
    preamble = preamble.replace("../../Source/", (ROOT / "Source").as_posix() + "/")
    preamble += between(header, "// XInput headers", "unsigned short Lang")
    preamble += between(header, "struct _TouchData", "_TouchData Touch1;")
    preamble += header[header.index("double StickDeviationPercent"):]
    preamble += """
struct State { _TouchData t1{}, t2{}; DS4_TOUCH last{}; bool valid = false; uint8_t packet = 0; XboxTouchpad::State stick; };
struct Config { bool swap = false, disable = false, share = false, click = false, ix = false, iy = false; XboxTouchpad::Settings touch; bool motionEnabled = false; int motionKey = XINPUT_GAMEPAD_RIGHT_SHOULDER; XboxMotion::Settings motion; };
struct Result { DS4_REPORT_EX report; unsigned motions; bool modifier; };
void check(bool ok, const char* message) { if (!ok) { std::fprintf(stderr, "FAIL: %s\\n", message); std::exit(1); } }
"""
    tests = r"""
int main() {
    unsigned long long cases = 0;
    const BYTE values[] = {0,1,127,255};
    for (int flags = 0; flags < 16; ++flags) for (unsigned buttons = 0; buttons < 65536; ++buttons)
        for (BYTE lt : values) for (BYTE rt : values) {
            Config c; c.swap = flags & 1; c.disable = flags & 2; c.share = flags & 4; c.click = flags & 8;
            XINPUT_STATE x{}; x.Gamepad.wButtons = WORD(buttons); x.Gamepad.bLeftTrigger = lt; x.Gamepad.bRightTrigger = rt;
            x.Gamepad.sThumbLX = 18000; x.Gamepad.sThumbLY = -12000; x.Gamepad.sThumbRX = -24000; x.Gamepad.sThumbRY = 32767;
            State a,b; auto old = original(x,c,a), now = updated(x,c,b);
            check(std::memcmp(&old.report,&now.report,sizeof(DS4_REPORT_EX)) == 0 && old.motions == now.motions,
                "legacy entire report byte identical to trigger fix baseline");
            ++cases;
        }
    unsigned long long modern = 0;
    for (auto mode : {XboxTouchpad::Mode::Absolute, XboxTouchpad::Mode::Relative})
    for (int flags = 0; flags < 64; ++flags) for (unsigned buttons = 0; buttons < 65536; ++buttons) {
        Config c; c.swap = flags & 1; c.disable = flags & 2; c.share = flags & 4; c.click = flags & 8;
        c.ix = flags & 16; c.iy = flags & 32; c.touch.mode = mode; c.touch.curve = XboxTouchpad::Curve::Quadratic;
        XINPUT_STATE x{}; x.Gamepad.wButtons = WORD(buttons); x.Gamepad.bLeftTrigger = 89; x.Gamepad.bRightTrigger = 207;
        x.Gamepad.sThumbLX = 12000; x.Gamepad.sThumbRX = -24000; x.Gamepad.sThumbRY = 32767;
        State a,b; auto old = original(x,c,a), now = updated(x,c,b);
        check(old.motions == now.motions && old.modifier == now.modifier, "motion activation unchanged");
        check(old.report.wButtons == now.report.wButtons && old.report.bSpecial == now.report.bSpecial
            && old.report.bTriggerL == now.report.bTriggerL && old.report.bTriggerR == now.report.bTriggerR,
            "all buttons and triggers unchanged in modern modes");
        check(old.report.bThumbLX == now.report.bThumbLX && old.report.bThumbLY == now.report.bThumbLY
            && old.report.bThumbRX == now.report.bThumbRX && old.report.bThumbRY == now.report.bThumbRY,
            "normal and suppressed sticks unchanged");
        check(std::memcmp(&old.report.wGyroX,&now.report.wGyroX,12) == 0, "gyro and accel unchanged");
        check(std::memcmp(&old.report.sCurrentTouch.bIsUpTrackingNum2,&now.report.sCurrentTouch.bIsUpTrackingNum2,4) == 0,
            "left stick second touch unchanged");
        ++modern;
    }
    Config c; c.touch.mode = XboxTouchpad::Mode::Relative; c.touch.curve = XboxTouchpad::Curve::Quadratic;
    XINPUT_STATE x{}; x.Gamepad.wButtons = XINPUT_GAMEPAD_BACK; x.Gamepad.bRightTrigger = 200;
    x.Gamepad.bLeftTrigger = 77; x.Gamepad.sThumbRX = -32768; x.Gamepad.sThumbRY = 32767;
    State state;
    for (int i = 0; i < 300; ++i) {
        auto now = updated(x,c,state);
        check(now.report.bTriggerL == 77 && now.report.bTriggerR == 200, "held LT/RT during relative motion");
        check((now.report.wButtons & (DS4_BUTTON_TRIGGER_LEFT|DS4_BUTTON_TRIGGER_RIGHT))
            == (DS4_BUTTON_TRIGGER_LEFT|DS4_BUTTON_TRIGGER_RIGHT), "held trigger flags");
        check(!(now.report.sCurrentTouch.bIsUpTrackingNum1 & 0x80), "continuous touch down");
        check(state.t1.ID == 1, "stable tracking id");
    }
    check(state.t1.X == 0 && state.t1.Y == 0 && state.t1.IsChanged, "(0,0) contact stays down");
    x.Gamepad.sThumbRX = x.Gamepad.sThumbRY = 0;
    auto held = updated(x,c,state);
    check(state.t1.X == 0 && state.t1.Y == 0, "neutral preserves top left");
    x.Gamepad.wButtons = 0; auto released = updated(x,c,state);
    check((released.report.sCurrentTouch.bIsUpTrackingNum1 & 0x80) && !state.stick.active, "finger up on modifier release");
    x.Gamepad.wButtons = XINPUT_GAMEPAD_BACK; auto restarted = updated(x,c,state);
    check(state.t1.X == 960 && state.t1.Y == 471 && state.t1.ID == 2, "repress starts new center contact");
    c.touch.mode = XboxTouchpad::Mode::Absolute;
    x.Gamepad.sThumbRX = 16000; x.Gamepad.sThumbRY = 8000;
    State direction; auto direct = updated(x,c,direction);
    check(direction.t1.X > 960 && direction.t1.Y < 471, "normal absolute X/Y direction");
    c.ix = c.iy = true; direction = {}; auto inverted = updated(x,c,direction);
    check(direction.t1.X < 960 && direction.t1.Y > 471, "existing InvertX/Y settings honored");

    unsigned long long analog = 0;
    for (int key : {XINPUT_GAMEPAD_RIGHT_SHOULDER, XINPUT_GAMEPAD_RIGHT_THUMB, 0, XINPUT_GAMEPAD_BACK})
    for (int flags = 0; flags < 16; ++flags) for (unsigned buttons = 0; buttons < 65536; ++buttons) {
        Config cfg; cfg.motionEnabled = true; cfg.motionKey = key;
        cfg.swap = flags & 1; cfg.disable = flags & 2; cfg.share = flags & 4; cfg.click = flags & 8;
        XINPUT_STATE input{}; input.Gamepad.wButtons = WORD(buttons);
        input.Gamepad.bLeftTrigger = 77; input.Gamepad.bRightTrigger = 200;
        input.Gamepad.sThumbLX = 12000; input.Gamepad.sThumbLY = -9000;
        input.Gamepad.sThumbRX = 32767; input.Gamepad.sThumbRY = 0;
        State before, after;
        auto actual = updated(input,cfg,after);
        bool eligible = key != 0 && (buttons & key) && !(buttons & XINPUT_GAMEPAD_BACK)
            && !(cfg.swap && key == XINPUT_GAMEPAD_RIGHT_SHOULDER);
        if (eligible) input.Gamepad.wButtons &= ~key;
        auto expected = original(input,cfg,before);
        if (eligible) {
            expected.report.bThumbRX = expected.report.bThumbRY = 128;
            expected.report.wGyroX = 0; expected.report.wGyroY = -960; expected.report.wGyroZ = 0;
            expected.report.wAccelX = 0; expected.report.wAccelY = 8192; expected.report.wAccelZ = 0;
        }
        check(std::memcmp(&expected.report,&actual.report,sizeof(DS4_REPORT_EX)) == 0,
            "analog routing, reserved key, right-stick suppression, triggers, Back priority and swap compatibility");
        ++analog;
    }
    Config motion; motion.motionEnabled = true;
    XINPUT_STATE heldMotion{}; heldMotion.Gamepad.wButtons = XINPUT_GAMEPAD_RIGHT_SHOULDER;
    heldMotion.Gamepad.bRightTrigger = 231;
    State contact;
    for (int i=0; i<20; ++i) {
        heldMotion.Gamepad.sThumbRX = i % 2 ? 32767 : -32768;
        auto r = updated(heldMotion,motion,contact);
        check(r.report.bTriggerR == 231 && (r.report.wButtons & DS4_BUTTON_TRIGGER_RIGHT), "RT stays active during analog gyro");
        check(r.report.wGyroY == (i % 2 ? -960 : 960), "analog horizontal sign and repeated samples");
        check(r.report.sCurrentTouch.bIsUpTrackingNum1 & 0x80, "motion does not create a touch");
    }
    heldMotion.Gamepad.sThumbRX = 0; auto stopped = updated(heldMotion,motion,contact);
    check(stopped.report.wGyroX == 0 && stopped.report.wGyroY == 0 && stopped.report.wGyroZ == 0,
        "neutral stops gyro immediately");
    heldMotion.Gamepad.wButtons = 0; heldMotion.Gamepad.sThumbRX = 32767;
    auto normal = updated(heldMotion,motion,contact);
    check(normal.report.bThumbRX == 255 && normal.report.wAccelY == 0, "key release restores normal stick and sensor source");
    std::printf("PASS: %llu enabled analog full-report comparisons, RT, touch-up, neutral and release.\n", analog);
    std::printf("PASS: %llu legacy full reports, %llu modern button/stick/motion comparisons; corner, release, tracking, LT/RT.\n", cases,modern);
}
"""
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "xbox_report_regression.cpp").write_text(preamble + mapper(old, "original") + mapper(new, "updated") + tests, encoding="utf-8-sig")
    print("PASS: trigger-fix block and stick-suppression block unchanged; generated real-source report regression.")


if __name__ == "__main__":
    main()
