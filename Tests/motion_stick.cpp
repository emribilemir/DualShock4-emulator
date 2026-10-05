#include "../Source/XboxMotion.h"
#include <cstdio>
#include <cstdlib>
#include <limits>
void check(bool ok, const char* message) { if (!ok) { std::fprintf(stderr,"FAIL: %s\n",message); std::exit(1); } }
int main() {
    XboxMotion::Settings s;
    auto full = XboxMotion::Calculate(32767,0,s);
    check(full.gyro[0] == 0 && full.gyro[1] == -960 && full.gyro[2] == 0,"horizontal mouse-equivalent axis and speed");
    check(XboxMotion::Calculate(-32768,0,s).gyro[1] == 960,"negative full normalization");
    check(XboxMotion::Calculate(0,32767,s).gyro[0] == 960,"up is positive gyro X, as mouse up");
    check(XboxMotion::Calculate(0,-32768,s).gyro[0] == -960,"down sign");
    check(XboxMotion::Calculate(3932,0,s).gyro[1] == 0,"radial deadzone");
    check(XboxMotion::Calculate(6553,0,s).gyro[1] == -8,"20 percent quadratic fine control");
    check(XboxMotion::Calculate(9830,0,s).gyro[1] == -40,"30 percent quadratic control");
    auto diagonal = XboxMotion::Calculate(32767,32767,s);
    check(std::abs(std::hypot(diagonal.gyro[0],diagonal.gyro[1])-960) < 1,"no diagonal speed boost");
    s.quadratic = false; check(XboxMotion::Calculate(6553,0,s).gyro[1] == -87,"linear response");
    s.horizontal = XboxMotion::Axis::Z; s.invertHorizontal = false;
    check(XboxMotion::Calculate(32767,0,s).gyro[2] == 960,"roll axis selection and inversion");
    s.invertVertical = true; check(XboxMotion::Calculate(0,32767,s).gyro[0] == -960,"vertical inversion");
    s.speed=2000; s.deadzone=0; s.Validate();
    check(XboxMotion::Calculate(32767,0,s).gyro[2] == 32000,"maximum rate safe in signed report");
    s.speed=std::numeric_limits<double>::quiet_NaN(); s.deadzone=1; s.horizontal=s.vertical; s.Validate();
    check(s.speed==60 && s.deadzone==.95 && s.horizontal != s.vertical,"config validation");
    check(XboxMotion::ParseAxis("z",XboxMotion::Axis::X)==XboxMotion::Axis::Z,"axis case-insensitive");
    check(XboxMotion::ParseAxis("bad",XboxMotion::Axis::Y)==XboxMotion::Axis::Y,"axis fallback");
    // The same angular velocity integrates to the same angle at different polling rates.
    s= {}; auto r= XboxMotion::Calculate(9830,0,s);
    for (int hz : {30,60,250,1000}) {
        double angle=0;
        for (int i=0;i<hz*2;++i) angle += r.gyro[1]/16.0/hz;
        check(std::abs(angle+5.0)<1e-9,"polling independent angular rate");
    }
    std::puts("PASS: analog gyro axes, speed, deadzone, curves, inversion, bounds and polling rates.");
}
