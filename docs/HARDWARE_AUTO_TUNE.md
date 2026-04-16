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
```

## Force laptop-safe mode

```env
TISH_FORCE_LAPTOP_SAFE=1
```
