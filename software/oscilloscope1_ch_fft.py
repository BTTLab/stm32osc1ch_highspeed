import serial
import struct
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import Button
from scipy.signal import resample

PORT = "/dev/cu.usbmodemXXXXX"   # macOS
# PORT = "COMXX"                 # Windows

BAUD = 921600

SAMPLES = 4096

ADC_VREF = 3.3
ADC_MAX = 4095

SAMPLE_RATE = 6_000_000
FS_PER_CHANNEL = SAMPLE_RATE / 3

TRIGGER_LEVEL = 700
PRE_TRIGGER = 1024

UPSAMPLE_FACTOR = 8

APERTURE_GAIN_LIMIT = 3.0

APERTURE_COMPENSATION_ENABLED = False

# Initial state of the display upsampling method toggle
# (can be switched later with the "FFT: ON/OFF" button in the plot window):
#   True  -> band-limited (sinc) reconstruction via FFT (scipy.signal.resample).
#            Renders the signal shape more accurately at high frequencies,
#            close to Nyquist, but is more computationally expensive and
#            requires mirror-padding the edges (see upsample_fft) to avoid
#            ringing artifacts.
#   False -> plain linear interpolation (np.interp). Faster and always safe
#            (no edge artifacts), but looks less smooth ("blocky") at high
#            frequencies.
FFT_UPSAMPLE_ENABLED = False


time_axis = np.linspace(0, (SAMPLES - 1) / SAMPLE_RATE * 1e6, SAMPLES * UPSAMPLE_FACTOR)

ser = serial.Serial(
    PORT,
    BAUD,
    timeout=2
)
ser.reset_input_buffer()

signal = np.zeros(SAMPLES)
voltage = np.zeros(SAMPLES * UPSAMPLE_FACTOR)


def read_frame():
    while True:

        b = ser.read(1)

        if not b:
            return None

        if b[0] == 0xAA:

            b2 = ser.read(1)

            if b2 and b2[0] == 0x55:
                break

    header = ser.read(4)

    if len(header) != 4:
        return None

    trig_prev, trig_curr = struct.unpack("<HH", header)

    data = ser.read(SAMPLES * 2)

    if len(data) != SAMPLES * 2:
        return None

    values = struct.unpack(
        "<" + "H" * SAMPLES,
        data
    )

    return np.array(values, dtype=np.float64), trig_prev, trig_curr


def align_trigger(sig, trig_prev, trig_curr):
    denom = trig_curr - trig_prev

    if denom == 0:
        frac = 1.0
    else:
        frac = (TRIGGER_LEVEL - trig_prev) / denom

    frac = min(max(frac, 0.0), 1.0)

    shift = frac - 1.0

    x = np.arange(len(sig))
    return np.interp(x + shift, x, sig)


def aperture_compensate(sig, fs, fs_per_channel, gain_limit=APERTURE_GAIN_LIMIT):
    n = len(sig)
    spec = np.fft.rfft(sig)
    freqs = np.fft.rfftfreq(n, d=1 / fs)

    x = np.pi * freqs / fs_per_channel
    correction = np.ones_like(x)

    nonzero = x != 0
    correction[nonzero] = x[nonzero] / np.sin(x[nonzero])

    correction = np.clip(correction, 0, gain_limit)

    spec_corrected = spec * correction
    return np.fft.irfft(spec_corrected, n)


def upsample_fft(sig, factor=UPSAMPLE_FACTOR):
    """
    Band-limited (sinc) reconstruction via FFT. Mirror-pads the edges before
    resampling to remove ringing at the window boundaries (FFT treats the
    signal as periodic, and the start/end values usually don't match).
    """
    n = len(sig)
    pad = max(n // 4, 1)

    left_mirror = sig[pad:0:-1]
    right_mirror = sig[-2:-pad - 2:-1]
    padded = np.concatenate([left_mirror, sig, right_mirror])

    up_padded = resample(padded, len(padded) * factor)

    start = pad * factor
    end = start + n * factor
    return up_padded[start:end]


def upsample_linear(sig, factor=UPSAMPLE_FACTOR):
    """
    Plain linear interpolation between samples. Does not reconstruct the
    true signal shape as accurately as the FFT-based method, but has no
    edge artifacts and runs faster.
    """
    n = len(sig)
    x = np.arange(n)
    x_up = np.linspace(0, n - 1, n * factor)
    return np.interp(x_up, x, sig)


def upsample_for_display(sig, factor=UPSAMPLE_FACTOR):
    if FFT_UPSAMPLE_ENABLED:
        return upsample_fft(sig, factor)
    return upsample_linear(sig, factor)


fig, ax = plt.subplots()

line, = ax.plot(
    time_axis,
    voltage
)

ax.set_ylim(
    0,
    ADC_VREF
)

ax.set_xlim(
    0,
    time_axis[-1]
)

ax.set_xlabel(
    "Time (us)"
)

ax.set_ylabel(
    "Voltage (V)"
)

ax.grid()

# Leave some space at the bottom for the button
plt.subplots_adjust(bottom=0.15)

button_ax = plt.axes([0.81, 0.02, 0.15, 0.06])


def _button_label():
    return f"FFT: {'ON' if FFT_UPSAMPLE_ENABLED else 'OFF'}"


fft_button = Button(button_ax, _button_label())


def toggle_fft(event):
    global FFT_UPSAMPLE_ENABLED
    FFT_UPSAMPLE_ENABLED = not FFT_UPSAMPLE_ENABLED
    fft_button.label.set_text(_button_label())
    fig.canvas.draw_idle()


fft_button.on_clicked(toggle_fft)


def update(frame):

    global signal
    global voltage

    result = read_frame()

    if result is not None:
        data, trig_prev, trig_curr = result
        signal = data

        aligned = align_trigger(signal, trig_prev, trig_curr)

        if APERTURE_COMPENSATION_ENABLED:
            aligned = aperture_compensate(aligned, SAMPLE_RATE, FS_PER_CHANNEL)

        upsampled = upsample_for_display(aligned)

        voltage = (
            upsampled *
            ADC_VREF /
            ADC_MAX
        )

        line.set_ydata(
            voltage
        )

    return line,


ani = FuncAnimation(
    fig,
    update,
    interval=100,
    blit=True
)
plt.show()
