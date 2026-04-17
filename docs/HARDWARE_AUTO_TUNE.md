# Hardware Auto-Tune

The analyzer now auto-adjusts performance settings at startup based on local hardware:

- CPU threads
- CPU model class (including laptop U/H/HS/HX chips)
- RAM size
- GPU presence/type (Windows)

If a laptop-class CPU is detected (for example `Ryzen 7 5800U`) and there is no discrete GPU,
the app switches to `laptop_safe` mode automatically.

## What gets tuned

- `max_large`
- `max_niche`
- `max_per_query`
- `parallel`
- `page_timeout`
- `vision_timeout_sec`
- `vision_num_predict`
- `vision_model` (fallback to an available vision model if configured one is missing)
- `vision_slow_threshold_ms` (auto-degrade threshold for slow AI responses)

On low-end/laptop-safe profiles, guardrails are applied automatically:

- caps for heavy runtime values (`parallel`, `vision_num_predict`, screenshot size, etc.)
- forced turbo prompt mode
- prompt examples disabled
- screenshot format forced to `jpeg`

## Disable auto-tune

Set environment variable:

```env
TISH_DISABLE_HW_AUTOTUNE=1
```

## Optional manual overrides

```env
TISH_VISION_TIMEOUT_SEC=420
TISH_VISION_NUM_PREDICT=320
TISH_PARALLEL_SHOTS=2
TISH_SEARCH_MAX_PASSES=6
TISH_SCREENSHOT_WAIT_MIN_MS=180
TISH_SCREENSHOT_WAIT_MAX_MS=420
TISH_SCREENSHOT_WIDTH=1024
TISH_SCREENSHOT_HEIGHT=640
TISH_SCREENSHOT_FORMAT=jpeg
TISH_SCREENSHOT_QUALITY=60
TISH_ANALYSIS_PROMPT_MODE=turbo
TISH_USE_EXAMPLES_IN_PROMPT=0
TISH_AUTO_SWITCH_VISION_MODEL=1
TISH_VISION_SLOW_THRESHOLD_MS=55000
```

`TISH_AUTO_SWITCH_VISION_MODEL` is optional and disabled by default.

## Force laptop-safe mode

```env
TISH_FORCE_LAPTOP_SAFE=1
```
