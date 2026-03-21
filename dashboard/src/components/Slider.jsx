import * as SliderPrimitive from '@radix-ui/react-slider'
import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import { useState, useEffect, useCallback, forwardRef } from 'react'

// ── Tooltip ───────────────────────────────────────────────────────────────────

function SliderTooltip({ open, content, side = 'top', children }) {
  return (
    <TooltipPrimitive.Provider delayDuration={0}>
      <TooltipPrimitive.Root open={open}>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            sideOffset={8}
            side={side}
            style={{
              zIndex: 50,
              backgroundColor: '#1C1C1E',
              color: '#FFFFFF',
              fontSize: 11,
              fontWeight: 700,
              borderRadius: 7,
              padding: '4px 9px',
              fontFamily: '"Plus Jakarta Sans", sans-serif',
              pointerEvents: 'none',
              userSelect: 'none',
            }}
          >
            {content}
            <TooltipPrimitive.Arrow style={{ fill: '#1C1C1E' }} />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  )
}

// ── Slider ────────────────────────────────────────────────────────────────────
// Key design decision: pass `value` DIRECTLY to SliderPrimitive.Root so Radix
// manages the drag state internally — never route it through React state, which
// would snap the thumb every re-render.

const Slider = forwardRef(function Slider(
  { value, defaultValue, onValueChange, tooltipContent,
    min = 0, max = 100, step = 1, orientation = 'horizontal',
    disabled, ...props },
  ref,
) {
  // displayValue is ONLY used for the tooltip label — not for thumb position.
  const [displayValue, setDisplayValue] = useState(
    value?.[0] ?? defaultValue?.[0] ?? min,
  )
  const [showTooltip, setShowTooltip] = useState(false)

  const handleValueChange = (newValue) => {
    setDisplayValue(newValue[0])
    onValueChange?.(newValue)
  }

  const handlePointerUp = useCallback(() => setShowTooltip(false), [])
  useEffect(() => {
    document.addEventListener('pointerup', handlePointerUp)
    return () => document.removeEventListener('pointerup', handlePointerUp)
  }, [handlePointerUp])

  const isVertical = orientation === 'vertical'

  return (
    <SliderPrimitive.Root
      ref={ref}
      value={value}
      defaultValue={defaultValue}
      min={min}
      max={max}
      step={step}
      orientation={orientation}
      disabled={disabled}
      onValueChange={handleValueChange}
      style={{
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        userSelect: 'none',
        touchAction: 'none',
        width: isVertical ? 'auto' : '100%',
        height: isVertical ? '100%' : 20,
        opacity: disabled ? 0.4 : 1,
        cursor: disabled ? 'not-allowed' : 'default',
      }}
      {...props}
    >
      <SliderPrimitive.Track
        style={{
          position: 'relative',
          flexGrow: 1,
          borderRadius: 999,
          overflow: 'hidden',
          backgroundColor: '#E5E5EA',
          ...(isVertical
            ? { width: 4, height: '100%' }
            : { height: 4, width: '100%' }),
        }}
      >
        <SliderPrimitive.Range
          style={{
            position: 'absolute',
            backgroundColor: '#34C759',
            ...(isVertical ? { width: '100%' } : { height: '100%' }),
          }}
        />
      </SliderPrimitive.Track>

      <SliderTooltip
        open={showTooltip}
        content={tooltipContent ? tooltipContent(displayValue) : displayValue}
        side={isVertical ? 'right' : 'top'}
      >
        <SliderPrimitive.Thumb
          className="slider-thumb"
          onPointerDown={() => setShowTooltip(true)}
          style={{
            display: 'block',
            width: 18,
            height: 18,
            borderRadius: '50%',
            backgroundColor: '#34C759',
            border: '2.5px solid #fff',
            boxShadow: '0 1px 6px rgba(0,0,0,0.20)',
            cursor: disabled ? 'not-allowed' : 'grab',
            outline: 'none',
          }}
        />
      </SliderTooltip>
    </SliderPrimitive.Root>
  )
})

export { Slider }
