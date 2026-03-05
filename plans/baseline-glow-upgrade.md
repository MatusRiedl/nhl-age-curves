# Plan: Add subtle glow under baseline curve

## Goal
Add `fill='tozeroy'` with 5% opacity to the baseline data line in the NHL age curves chart.

## File to Modify
- [`nhl/chart.py`](nhl/chart.py:294-297)

## Current Code (lines 294-297)
```python
elif "Baseline" in trace.name:
    trace.line.dash          = 'dash'
    trace.line.color         = 'rgba(255, 255, 255, 0.4)'
    trace.marker.size        = 1
```

## New Code
```python
elif "Baseline" in trace.name:
    trace.line.dash          = 'dash'
    trace.line.color         = 'rgba(255, 255, 255, 0.4)'
    trace.marker.size        = 1
    trace.fill               = 'tozeroy'
    trace.fillcolor          = 'rgba(255, 255, 255, 0.05)'
```

## Explanation
- `fill='tozeroy'` - fills the area under the curve down to the x-axis
- `fillcolor='rgba(255, 255, 255, 0.05)'` - white at 5% opacity creates the subtle glow effect

This is a minimal, surgical change that adds the visual effect without affecting other traces.
