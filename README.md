# stm32osc1ch_highspeed
# STM32 DIY Oscilloscope — 6 MSPS



A DIY digital oscilloscope built around the STM32F207ZG and its three built-in ADCs.

This is the third version of the oscilloscope project. The previous version used all three ADCs in **Triple Regular Simultaneous Mode** to provide three independent channels at up to 2 MSPS per channel.

This version takes a different approach: all three ADCs are used to sample the **same input signal** with precisely shifted sampling times. This is known as **Triple Interleaved Mode** and allows the three ADCs to effectively behave as a single ADC with a sampling rate of up to **6 MSPS**.

The project also introduces **FFT-based waveform reconstruction**, which can be used to produce a smoother and more visually useful representation of high-frequency signals.

This is primarily an educational and experimental project intended to demonstrate the principles behind high-speed ADC acquisition, interleaved sampling, DMA, UART data transfer, and signal reconstruction.

It is **not intended to replace a commercial oscilloscope**.

## Features

* Up to **6 MSPS effective sampling rate**
* STM32F207ZG MCU
* Three built-in 12-bit ADCs
* **Triple Interleaved ADC mode**
* All three ADCs sample the same input signal
* ADC sampling controlled by a hardware timer
* DMA-based acquisition
* 1024-sample waveform acquisition
* Rising-edge triggering
* UART transfer to a PC
* Python-based oscilloscope front end
* Real-time waveform display
* Optional **FFT-based waveform reconstruction**
* Waveform reconstruction with mirrored signal extensions to reduce edge artifacts
* Reconstruction can be enabled or disabled from the GUI

## How Triple Interleaved Mode Works

Normally, each ADC can independently sample a signal. In the previous version of this project, the three ADCs were used simultaneously to create three oscilloscope channels.

Here, all three ADCs are connected to the **same physical input**.

The ADCs are triggered by the same timer, but their conversions are shifted in time relative to each other:

```text
ADC1: |----S----|----S----|----S----|----S----|
ADC2:    |----S----|----S----|----S----|----S----|
ADC3:       |----S----|----S----|----S----|----S----|

Combined:

      S   S   S   S   S   S   S   S   S   S   S
      <----------- effective 6 MSPS ------------>
```

With each ADC operating at 2 MHz, the three interleaved ADCs provide an effective sampling rate of:

```text
2 MSPS × 3 = 6 MSPS
```

The minimum inter-ADC delay in this configuration is **5 ADC clock cycles**, which limits the practical maximum sampling rate.

In theory, reducing the ADC resolution could allow an even higher effective sampling rate, approaching approximately 10 MSPS, but this version uses the full 12-bit ADC resolution.

## Hardware

The project is designed for:

* **NUCLEO-F207ZG**
* MCU: **STM32F207ZGT6**

The three ADCs must be connected to the **same physical signal**.

An important detail is that an ADC channel number does **not necessarily correspond to the same physical pin on every ADC**.

For example, `ADC_CHANNEL_6` corresponds to:

```text
ADC1 → PA6
ADC2 → PA6
ADC3 → PF8
```

Therefore, configuring all three ADCs for channel 6 does **not** mean that all three ADCs are measuring the same pin.

This can result in two ADCs measuring the intended signal while the third ADC measures an unrelated input.

For this reason, the current version uses a physical pin that can be connected to all three ADCs.

### Input voltage

The STM32 ADC inputs must remain within the MCU's allowed input voltage range.

**Do not connect signals outside the allowed voltage range directly to the ADC.**

A suitable analog front end, including protection, attenuation, buffering and/or level shifting, should be used for real measurements.

## CubeMX Configuration

The important ADC configuration is:

```text
ADC1:
    Mode: Triple Interleaved Mode

ADC2:
    Enabled
    Same analog input

ADC3:
    Enabled
    Same analog input

ADC resolution:
    12 bit

Inter-ADC sampling delay:
    5 cycles (minimum)

External trigger:
    Timer

DMA:
    Enabled
```

ADC1 acts as the **master ADC**.

Unlike the previous version, the DMA is started using:

```c
HAL_ADCEx_MultiModeStart_DMA(...)
```

The other two ADCs must also be started during initialization.

## ADC Data Format

One of the main differences from the previous version is the format of the data produced by Triple Interleaved Mode.

The DMA buffer contains packed **32-bit words**, with multiple ADC results stored inside them.

This format is not particularly convenient for normal oscilloscope processing.

The firmware therefore treats the DMA buffer as an array of 16-bit values and provides a helper function that returns the sample corresponding to a requested sample index.

Conceptually, the resulting stream is converted into:

```text
sample 0
sample 1
sample 2
sample 3
sample 4
...
```

where consecutive samples originate from different ADC conversions.

The rest of the oscilloscope firmware can therefore operate on a normal sequential stream of 16-bit ADC samples instead of dealing directly with the packed multi-ADC DMA format.

## Firmware

The firmware was generated using **STM32CubeMX / STM32CubeIDE** and uses the STM32F2 HAL.

The important changes compared with the previous 3-channel version include:

* Triple Interleaved ADC configuration
* ADC2 and ADC3 startup
* `HAL_ADCEx_MultiModeStart_DMA()` for ADC1
* New handling of the packed Triple Interleaved DMA format
* 16-bit sample extraction from the DMA buffer
* Additional ADC/DMA callback handling
* Changes to data types and buffer definitions
* Improved UART transmission handling

The UART code also prevents a new packet transmission from starting while the previous packet is still being transmitted.

This is important because the ADC can acquire data faster than the UART can transfer it.

## PC Software

The PC front end is written in Python and uses:

* **PySerial** for communication
* **NumPy** for numerical processing
* **Matplotlib** for waveform display
* FFT/IFFT processing for optional waveform reconstruction

Install the dependencies:

```bash
cd software
pip install -r requirements.txt
```

Configure the serial port in the Python application:

```python
PORT = "COM5"
```

For macOS, for example:

```python
PORT = "/dev/cu.usbmodemXXXXX"
```

Then run:

```bash
python oscilloscope.py
```

The exact Python filename may differ depending on the contents of the `software/` directory.

## FFT Waveform Reconstruction

At 6 MSPS, a theoretical Nyquist frequency of:

```text
6 MSPS / 2 = 3 MHz
```

is obtained.

This does **not** mean that a 3 MHz waveform will necessarily look good on the oscilloscope.

At high frequencies there may only be a few samples per period. Simply connecting adjacent samples with straight lines can therefore make a smooth analog waveform appear jagged or distorted.

To improve the visual reconstruction, the Python application includes an optional **FFT reconstruction** mode.

The basic processing pipeline is:

```text
Time-domain samples
        ↓
Edge extension
        ↓
FFT
        ↓
Frequency-domain processing
        ↓
IFFT
        ↓
Remove extensions
        ↓
Reconstructed waveform
```

The reconstruction does not create new measured information.

It estimates the waveform between measured samples using the mathematical assumptions of the reconstruction process.

### Why edge extension is needed

Fourier processing normally assumes that the captured block is periodic:

```text
... [ waveform ][ waveform ][ waveform ] ...
```

In a real acquisition, however, the beginning and end of the captured block usually do not match.

This creates an artificial discontinuity when the FFT treats the block as periodic.

That discontinuity introduces additional frequency components and causes **spectral leakage**, which can appear as ringing and other artifacts in the reconstructed waveform.

To reduce this effect, the application mirrors parts of the signal at both ends before performing the reconstruction:

```text
        mirrored       original       mirrored
       /-------\    /------------\    /-------\
------/         \__/              \__/         \------
```

After reconstruction, the mirrored portions are removed and only the original central section is displayed.

## FFT Reconstruction: When to Use It

FFT reconstruction is particularly useful when displaying high-frequency sine waves where only a few samples are available per cycle.

For example, a **1 MHz sine wave** can look considerably smoother with reconstruction enabled.

However, reconstruction is not always better.

At lower frequencies, it can introduce visible artifacts that are not actually present in the measured signal.

For this reason, the GUI provides a button to enable or disable the reconstruction and compare the two results directly.

## Practical Bandwidth

Although the theoretical Nyquist frequency is approximately **3 MHz**, this should not be interpreted as the usable oscilloscope bandwidth.

During testing:

* Around **200 kHz** — waveform is reproduced very well
* Around **600 kHz** — noticeable waveform distortion begins
* Around **1 MHz** — waveform can still be made reasonably useful with FFT reconstruction
* Above **1 MHz** — waveform shape becomes increasingly difficult to distinguish reliably

Therefore, approximately **1 MHz** is a more realistic upper limit for useful waveform display in this implementation.

The exact result depends on the signal, analog front end, sampling phase, reconstruction settings and other hardware/software limitations.

## Sampling Jitter and Triggering

At higher frequencies, another limitation becomes apparent.

The sampling is not synchronized to the input signal. As a result, consecutive acquisitions can start at slightly different phases of the waveform.

This can cause the waveform to appear to move horizontally or **jitter** from acquisition to acquisition.

For example:

```text
Acquisition 1:    /¯\    /¯\
Acquisition 2:     /¯\    /¯\
Acquisition 3:   /¯\    /¯\
```

This is especially noticeable at higher frequencies.

A more sophisticated hardware trigger or additional front-end synchronization could potentially improve this behavior.

The current version does not attempt to solve this problem in hardware.

## Repository Structure

```text
stm32osc6msps/
├── firmware/
│   ├── Core/
│   │   ├── Inc/
│   │   └── Src/
│   ├── Drivers/
│   ├── *.ioc
│   └── ...
│
├── software/
│   ├── oscilloscope*.py
│   └── requirements.txt
│
├── README.md
└── LICENSE
```

The exact filenames may change as the project evolves.

## Getting Started

### 1. Firmware

Open the CubeMX/CubeIDE project located in the `firmware/` directory.

Build the project and flash it to a **NUCLEO-F207ZG**.

Make sure the three ADC inputs are connected to the same signal according to the selected CubeMX configuration.

### 2. Python software

Install the required packages:

```bash
cd software
pip install -r requirements.txt
```

Configure the serial port in the Python application.

Then start the oscilloscope:

```bash
python oscilloscope.py
```

### 3. Test signal

For an initial test, apply a DC voltage within the ADC input range.

Then try progressively higher-frequency sine waves.

A 200 kHz sine wave is a good starting point for verifying the increased sampling rate.

## From 2 MSPS to 6 MSPS

The main difference between the previous 3-channel version and this version can be summarized as follows:

```text
Previous version:

ADC1 ──→ Channel 1 ──→ 2 MSPS
ADC2 ──→ Channel 2 ──→ 2 MSPS
ADC3 ──→ Channel 3 ──→ 2 MSPS


This version:

             ┌─ ADC1 ─┐
Input ───────┼─ ADC2 ─┼──→ Interleaved samples ──→ 6 MSPS
             └─ ADC3 ─┘
```

The price is that the three independent channels are gone.

Instead, the three ADCs are combined to obtain a higher effective sampling rate on **one channel**.

## Limitations

This is an experimental oscilloscope and has several important limitations.

### Analog front end

The project does not provide a complete professional oscilloscope front end.

Input impedance, protection, attenuation, bandwidth and signal conditioning depend on the external circuitry.

**Do not connect potentially unsafe or out-of-range voltages directly to the STM32 ADC.**

### Effective bandwidth

A 6 MSPS sampling rate does not imply a 3 MHz usable analog bandwidth.

In practice, waveform reconstruction becomes increasingly unreliable at high frequencies.

Approximately **1 MHz** is considered a reasonable practical upper limit for useful waveform visualization in this implementation.

### Sampling jitter

The acquisition is not fully synchronized to the input signal.

At higher frequencies, this can cause horizontal movement of the waveform between acquisitions.

### FFT reconstruction artifacts

FFT reconstruction is an estimation technique and can introduce artifacts, especially when used on signals for which its assumptions are not appropriate.

It should not be interpreted as additional measurement accuracy.

### UART bandwidth

The waveform still has to be transferred from the STM32 to the PC over UART.

The serial link therefore limits the possible acquisition/update rate independently of the ADC sampling rate.

### ADC matching

The three ADCs are separate physical ADC peripherals. Their characteristics are not perfectly identical.

Small differences in offset, gain and conversion behavior can therefore affect the interleaved waveform.

### No hardware oscilloscope trigger

The current project does not implement a sophisticated hardware trigger comparable to a commercial oscilloscope.

## Previous Versions

This project is part of a series of experiments with the STM32F207's ADC peripherals.

### Version 1 — Single Channel

A single-channel oscilloscope using one ADC at up to 2 MSPS.

### Version 2 — Three Channels

Three ADCs used in **Triple Regular Simultaneous Mode**, providing:

```text
3 channels × 2 MSPS
```

See:

https://github.com/BTTLab/stm32osc3ch

### Version 3 — 6 MSPS Interleaved

Three ADCs are now combined using **Triple Interleaved Mode**:

```text
1 channel × 6 MSPS
```

This version also introduces FFT-based waveform reconstruction.

## What This Project Is

This project is not intended to be a ready-to-use laboratory oscilloscope.

Instead, it is an experiment and an educational example showing how the building blocks of an oscilloscope can be implemented using the peripherals already available inside an STM32 MCU:

* ADC
* DMA
* hardware timers
* UART
* triggering
* Python-based visualization
* FFT/IFFT signal processing
* interleaved ADC sampling

The goal is to understand how far the hardware can be pushed and what limitations appear along the way.

## License

This project is released under the **MIT License**.

See [LICENSE](LICENSE) for details.

## Disclaimer

This project is provided for educational and experimental purposes only.

It is **not a safety-critical measurement instrument** and should not be used for measurements where incorrect readings could result in damage, injury, or other hazardous consequences.

If you build your own version, make sure the analog input circuitry provides appropriate voltage limiting, protection and signal conditioning for your application.

